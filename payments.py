import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

import aiohttp

logger = logging.getLogger("payments")

BASE_DIR = Path(__file__).resolve().parent
PAYMENT_CONFIG_FILE = BASE_DIR / "payment_config.json"
PAYMENT_CONFIG_TXT_FILE = BASE_DIR / "payment_config.json.txt"

# USDT contracts
TRON_USDT_CONTRACT = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"
BSC_USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"

# Etherscan V2 chain IDs
BSC_CHAIN_ID = "56"

# Public RPC fallback for hash-based BEP20 checks
BSC_PUBLIC_RPC_URL = "https://bsc-dataseed.binance.org/"
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

PAYMENT_TOLERANCE_USDT = 0.05


class PaymentCheckResult(dict):
    """Small dict wrapper used by bot.py: paid, reason, amount, tx_hash, needs_manual_check."""



def _load_payment_config() -> Dict[str, Any]:
    """Берет ключи из payment_config.json, если файл есть.

    Дополнительно поддерживает payment_config.json.txt, потому что на некоторых хостингах
    файл загружают именно с таким именем. Это не ломает старый формат, но делает запуск надежнее.
    """
    for path in (PAYMENT_CONFIG_FILE, PAYMENT_CONFIG_TXT_FILE):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Cannot read {path.name}: {e}")
    return {}


_PAYMENT_CONFIG = _load_payment_config()


def _get_setting(name: str, default: str = "") -> str:
    """Сначала ищем переменную окружения, потом payment_config.json/payment_config.json.txt."""
    value = os.getenv(name)
    if value:
        return value.strip()

    value = _PAYMENT_CONFIG.get(name)
    if isinstance(value, str):
        return value.strip()

    return default


TRONGRID_API_KEY = _get_setting("TRONGRID_API_KEY")
ETHERSCAN_API_KEY = _get_setting("ETHERSCAN_API_KEY") or _get_setting("BSCSCAN_API_KEY")
TONCENTER_API_KEY = _get_setting("TONCENTER_API_KEY")
BSC_RPC_URL = _get_setting("BSC_RPC_URL", BSC_PUBLIC_RPC_URL)


def _amount_matches(tx_amount: float, expected_amount: Any) -> bool:
    try:
        expected = float(expected_amount)
    except (TypeError, ValueError):
        return False
    return abs(tx_amount - expected) <= PAYMENT_TOLERANCE_USDT


async def _get_json(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, headers=headers) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.error(f"Payment API returned non-JSON response: HTTP {resp.status} | {text[:300]}")
                return {}

            if resp.status >= 400:
                logger.error(f"Payment API HTTP error {resp.status}: {data}")
            return data


async def _post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.error(f"Payment RPC returned non-JSON response: HTTP {resp.status} | {text[:300]}")
                return {}

            if resp.status >= 400:
                logger.error(f"Payment RPC HTTP error {resp.status}: {data}")
            return data


# --- Address helpers ---
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_decode(value: str) -> bytes:
    number = 0
    for char in value:
        number *= 58
        if char not in _BASE58_ALPHABET:
            raise ValueError("invalid base58 character")
        number += _BASE58_ALPHABET.index(char)

    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    pad = 0
    for char in value:
        if char == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + raw


def _tron_base58_to_hex(address: str) -> str:
    try:
        decoded = _base58_decode(address)
    except ValueError:
        return ""
    if len(decoded) != 25:
        return ""
    payload, checksum = decoded[:-4], decoded[-4:]
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if checksum != digest:
        return ""
    return payload.hex().lower()


def _address_variants(address: str) -> Set[str]:
    value = str(address or "").strip().lower()
    if not value:
        return set()

    variants = {value}
    if value.startswith("0x"):
        variants.add(value[2:])
    if value.startswith("41") and len(value) == 42:
        variants.add("0x" + value[2:])
        variants.add(value[2:])

    tron_hex = _tron_base58_to_hex(str(address or "").strip())
    if tron_hex:
        variants.add(tron_hex)
        if tron_hex.startswith("41") and len(tron_hex) == 42:
            variants.add("0x" + tron_hex[2:])
            variants.add(tron_hex[2:])

    return variants


def _same_address(left: str, right: str) -> bool:
    return bool(_address_variants(left) & _address_variants(right))


def _parse_token_amount(raw_amount: Any, decimals: Any = 6) -> Optional[float]:
    if raw_amount is None:
        return None
    try:
        decimal_count = int(decimals or 6)
    except (TypeError, ValueError):
        decimal_count = 6

    raw_text = str(raw_amount).strip()
    if not raw_text:
        return None

    try:
        if "." in raw_text:
            value = float(raw_text)
            return value if value < 1_000_000 else value / (10 ** decimal_count)
        return int(raw_text, 10) / (10 ** decimal_count)
    except (TypeError, ValueError):
        try:
            return float(raw_text)
        except (TypeError, ValueError):
            return None


def _result(paid: bool, reason: str = "", amount: Optional[float] = None, tx_hash: str = "", needs_manual_check: bool = False) -> PaymentCheckResult:
    return PaymentCheckResult({
        "paid": paid,
        "reason": reason,
        "amount": amount,
        "tx_hash": tx_hash,
        "needs_manual_check": needs_manual_check,
    })


# --- Existing wallet-history checks ---
async def check_tron_payment(wallet: str, amount_usd: Any) -> bool:
    """Проверка входящей оплаты USDT TRC20 через TronGrid."""
    headers = {}
    if TRONGRID_API_KEY:
        headers["TRON-PRO-API-KEY"] = TRONGRID_API_KEY
    else:
        logger.warning("TRONGRID_API_KEY is empty. TRC20 check may be limited or fail.")

    url = f"https://api.trongrid.io/v1/accounts/{wallet}/transactions/trc20"
    params = {
        "limit": 30,
        "only_confirmed": "true",
        "contract_address": TRON_USDT_CONTRACT,
    }

    try:
        data = await _get_json(url, params=params, headers=headers)
        if not data.get("success", False):
            logger.info(f"TronGrid response is not success: {data}")
            return False

        for tx in data.get("data", []):
            to_address = str(tx.get("to", ""))
            token_info = tx.get("token_info") or {}
            contract = str(token_info.get("address", tx.get("contract_address", "")))

            if not _same_address(to_address, wallet):
                continue
            if contract and not _same_address(contract, TRON_USDT_CONTRACT):
                continue

            decimals = int(token_info.get("decimals", 6) or 6)
            value = int(tx.get("value", 0)) / (10 ** decimals)
            if _amount_matches(value, amount_usd):
                logger.info(f"TRC20 payment found: {value} USDT to {wallet}")
                return True

    except Exception as e:
        logger.error(f"Error checking TRC20 payment: {e}")

    return False


async def check_bsc_payment(wallet: str, amount_usd: Any) -> bool:
    """Проверка входящей оплаты USDT BEP20/BSC через Etherscan API V2."""
    if not ETHERSCAN_API_KEY:
        logger.warning("ETHERSCAN_API_KEY is empty. BEP20/BSC payment check cannot work.")
        return False

    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": BSC_CHAIN_ID,
        "module": "account",
        "action": "tokentx",
        "address": wallet,
        "contractaddress": BSC_USDT_CONTRACT,
        "page": 1,
        "offset": 30,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }

    try:
        data = await _get_json(url, params=params)
        status = str(data.get("status", ""))
        message = str(data.get("message", ""))
        result = data.get("result", [])

        if status != "1" or not isinstance(result, list):
            logger.info(f"Etherscan BSC response: status={status}, message={message}, result={result}")
            return False

        for tx in result:
            to_address = str(tx.get("to", ""))
            contract = str(tx.get("contractAddress", ""))

            if not _same_address(to_address, wallet):
                continue
            if not _same_address(contract, BSC_USDT_CONTRACT):
                continue

            decimals = int(tx.get("tokenDecimal", 18) or 18)
            value = int(tx.get("value", 0)) / (10 ** decimals)
            if _amount_matches(value, amount_usd):
                logger.info(f"BEP20/BSC payment found: {value} USDT to {wallet}, tx={tx.get('hash')}")
                return True

    except Exception as e:
        logger.error(f"Error checking BEP20/BSC payment: {e}")

    return False


async def check_ton_payment(wallet: str, amount_usd: Any) -> bool:
    """Заготовка под проверку USDT TON. Для полноценной проверки нужен Toncenter/TonAPI."""
    if not TONCENTER_API_KEY:
        logger.warning("TONCENTER_API_KEY is empty. TON payment check is not configured yet.")
    logger.info(f"TON payment check is not implemented yet: wallet={wallet}, amount={amount_usd}")
    return False


# --- Hash-based checks ---
async def check_tron_payment_by_hash(wallet: str, amount_usd: Any, tx_hash: str) -> PaymentCheckResult:
    """Проверяет конкретный TRC20 USDT перевод по TX hash через TronScan, затем TronGrid events."""
    tx_hash = str(tx_hash or "").strip()
    if not tx_hash:
        return _result(False, "empty_tx_hash", tx_hash=tx_hash)

    try:
        # TronScan обычно не требует ключ и по одному hash возвращает trc20TransferInfo.
        data = await _get_json("https://apilist.tronscanapi.com/api/transaction-info", params={"hash": tx_hash})
        if data:
            if data.get("confirmed") is False:
                return _result(False, "transaction_is_not_confirmed_yet", tx_hash=tx_hash)
            if data.get("contractRet") and str(data.get("contractRet")).upper() != "SUCCESS":
                return _result(False, f"transaction_status_{data.get('contractRet')}", tx_hash=tx_hash)

            transfers = data.get("trc20TransferInfo") or data.get("trc20TransferInfoList") or []
            for transfer in transfers:
                contract = transfer.get("contract_address") or transfer.get("contractAddress") or transfer.get("contract") or ""
                to_address = transfer.get("to_address") or transfer.get("to") or ""
                token_symbol = str(transfer.get("symbol") or transfer.get("tokenAbbr") or transfer.get("name") or "").upper()
                token_info = transfer.get("tokenInfo") or {}
                decimals = transfer.get("decimals") or transfer.get("tokenDecimal") or token_info.get("tokenDecimal") or 6
                raw_amount = transfer.get("amount_str") or transfer.get("amount") or transfer.get("value") or transfer.get("quant")
                value = _parse_token_amount(raw_amount, decimals)

                contract_ok = _same_address(contract, TRON_USDT_CONTRACT) or token_symbol == "USDT"
                if contract_ok and _same_address(to_address, wallet) and value is not None and _amount_matches(value, amount_usd):
                    return _result(True, "confirmed_by_tronscan_hash", amount=value, tx_hash=tx_hash)

        # Fallback: TronGrid events endpoint.
        headers = {"TRON-PRO-API-KEY": TRONGRID_API_KEY} if TRONGRID_API_KEY else {}
        events = await _get_json(f"https://api.trongrid.io/v1/transactions/{tx_hash}/events", headers=headers)
        for event in events.get("data", []):
            event_name = str(event.get("event_name") or event.get("event") or "").lower()
            if event_name != "transfer":
                continue
            result = event.get("result") or {}
            contract = event.get("contract_address") or result.get("contract_address") or ""
            to_address = result.get("to") or result.get("_to") or ""
            raw_amount = result.get("value") or result.get("_value")
            value = _parse_token_amount(raw_amount, 6)
            if _same_address(contract, TRON_USDT_CONTRACT) and _same_address(to_address, wallet) and value is not None and _amount_matches(value, amount_usd):
                return _result(True, "confirmed_by_trongrid_hash", amount=value, tx_hash=tx_hash)

    except Exception as e:
        logger.error(f"Error checking TRC20 hash {tx_hash}: {e}")
        return _result(False, "trc20_hash_check_error", tx_hash=tx_hash, needs_manual_check=True)

    return _result(False, "trc20_hash_not_matching_wallet_amount_or_token", tx_hash=tx_hash, needs_manual_check=True)


async def check_bsc_payment_by_hash(wallet: str, amount_usd: Any, tx_hash: str) -> PaymentCheckResult:
    """Проверяет конкретный BEP20 USDT перевод по TX hash через публичный BSC RPC без API-ключа."""
    tx_hash = str(tx_hash or "").strip()
    if not tx_hash:
        return _result(False, "empty_tx_hash", tx_hash=tx_hash)
    if not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash

    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash],
            "id": 1,
        }
        data = await _post_json(BSC_RPC_URL, payload)
        receipt = data.get("result")
        if not receipt:
            return _result(False, "transaction_receipt_not_found_yet", tx_hash=tx_hash, needs_manual_check=True)
        if str(receipt.get("status", "")).lower() != "0x1":
            return _result(False, "transaction_failed_or_not_successful", tx_hash=tx_hash)

        wallet_topic = "0x" + "0" * 24 + wallet.lower().replace("0x", "")
        contract_lower = BSC_USDT_CONTRACT.lower()

        for log in receipt.get("logs", []):
            address = str(log.get("address", "")).lower()
            topics = [str(t).lower() for t in log.get("topics", [])]
            if address != contract_lower:
                continue
            if len(topics) < 3 or topics[0] != TRANSFER_EVENT_TOPIC:
                continue
            if topics[2] != wallet_topic:
                continue
            raw_data = str(log.get("data", "0x0"))
            value = int(raw_data, 16) / (10 ** 18)
            if _amount_matches(value, amount_usd):
                return _result(True, "confirmed_by_bsc_rpc_hash", amount=value, tx_hash=tx_hash)

    except Exception as e:
        logger.error(f"Error checking BEP20 hash {tx_hash}: {e}")
        return _result(False, "bep20_hash_check_error", tx_hash=tx_hash, needs_manual_check=True)

    return _result(False, "bep20_hash_not_matching_wallet_amount_or_token", tx_hash=tx_hash, needs_manual_check=True)


async def check_ton_payment_by_hash(wallet: str, amount_usd: Any, tx_hash: str) -> PaymentCheckResult:
    """TON USDT/JETTON требует отдельной настройки TonAPI/Toncenter. Хэш сохраняем для ручной проверки."""
    tx_hash = str(tx_hash or "").strip()
    if not tx_hash:
        return _result(False, "empty_tx_hash", tx_hash=tx_hash)
    logger.info(f"TON hash received for manual check: wallet={wallet}, amount={amount_usd}, tx={tx_hash}")
    return _result(False, "ton_hash_saved_for_manual_check", tx_hash=tx_hash, needs_manual_check=True)


async def check_payment_by_hash(network: str, wallet: str, amount_usd: Any, tx_hash: str) -> PaymentCheckResult:
    network = str(network or "").upper()
    if network == "TRC20":
        return await check_tron_payment_by_hash(wallet, amount_usd, tx_hash)
    if network == "BEP20":
        return await check_bsc_payment_by_hash(wallet, amount_usd, tx_hash)
    if network == "TON":
        return await check_ton_payment_by_hash(wallet, amount_usd, tx_hash)
    return _result(False, "unsupported_network", tx_hash=str(tx_hash or "").strip())
