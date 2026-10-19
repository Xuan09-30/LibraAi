import ast
import math
import operator
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

import pytz
import requests


class FreeUtilityBelt:
    """
    100% Free, Local-First Everyday Smart Utility Belt for Project Libra v9.0.
    Provides:
      1. Live & Offline Currency/Crypto Conversion (Open ER API + deterministic fallback)
      2. Safe AST Mathematical, Percentage & Unit Evaluator (zero eval() risk)
      3. World Clock & Timezone Resolver (pytz + datetime)
      4. Network, Local IP & Ping Health Check (socket + 1.1.1.1 / 8.8.8.8 latency)
    """

    # Offline fallback rates relative to 1.0 USD
    OFFLINE_USD_RATES: Dict[str, float] = {
        "USD": 1.0,
        "MYR": 4.42,
        "SGD": 1.34,
        "EUR": 0.92,
        "GBP": 0.79,
        "JPY": 154.50,
        "CNY": 7.24,
        "THB": 34.60,
        "AUD": 1.53,
        "IDR": 15850.0,
        "KRW": 1395.0,
        "INR": 84.40,
        "HKD": 7.78,
        "TWD": 32.40,
        "BTC": 0.000011,
        "ETH": 0.00032,
    }

    CURRENCY_ALIASES: Dict[str, str] = {
        "usd": "USD",
        "us dollar": "USD",
        "us dollars": "USD",
        "dollar": "USD",
        "dollars": "USD",
        "bucks": "USD",
        "myr": "MYR",
        "rm": "MYR",
        "ringgit": "MYR",
        "malaysian ringgit": "MYR",
        "sgd": "SGD",
        "singapore dollar": "SGD",
        "singapore dollars": "SGD",
        "eur": "EUR",
        "euro": "EUR",
        "euros": "EUR",
        "gbp": "GBP",
        "pound": "GBP",
        "pounds": "GBP",
        "british pound": "GBP",
        "british pounds": "GBP",
        "jpy": "JPY",
        "yen": "JPY",
        "japanese yen": "JPY",
        "cny": "CNY",
        "rmb": "CNY",
        "yuan": "CNY",
        "renminbi": "CNY",
        "thb": "THB",
        "baht": "THB",
        "thai baht": "THB",
        "aud": "AUD",
        "australian dollar": "AUD",
        "australian dollars": "AUD",
        "idr": "IDR",
        "rupiah": "IDR",
        "krw": "KRW",
        "won": "KRW",
        "inr": "INR",
        "rupee": "INR",
        "rupees": "INR",
        "hkd": "HKD",
        "twd": "TWD",
        "btc": "BTC",
        "bitcoin": "BTC",
        "eth": "ETH",
        "ethereum": "ETH",
    }

    TIMEZONE_MAP: Dict[str, str] = {
        # Malaysia & Southeast Asia
        "kuala lumpur": "Asia/Kuala_Lumpur",
        "kl": "Asia/Kuala_Lumpur",
        "malaysia": "Asia/Kuala_Lumpur",
        "kuantan": "Asia/Kuala_Lumpur",
        "penang": "Asia/Kuala_Lumpur",
        "johor bahru": "Asia/Kuala_Lumpur",
        "kuching": "Asia/Kuching",
        "kota kinabalu": "Asia/Kuching",
        "singapore": "Asia/Singapore",
        "bangkok": "Asia/Bangkok",
        "thailand": "Asia/Bangkok",
        "jakarta": "Asia/Jakarta",
        "indonesia": "Asia/Jakarta",
        "manila": "Asia/Manila",
        "philippines": "Asia/Manila",
        "hanoi": "Asia/Bangkok",
        "vietnam": "Asia/Bangkok",
        # East Asia
        "tokyo": "Asia/Tokyo",
        "japan": "Asia/Tokyo",
        "seoul": "Asia/Seoul",
        "korea": "Asia/Seoul",
        "south korea": "Asia/Seoul",
        "beijing": "Asia/Shanghai",
        "shanghai": "Asia/Shanghai",
        "china": "Asia/Shanghai",
        "hong kong": "Asia/Hong_Kong",
        "taipei": "Asia/Taipei",
        "taiwan": "Asia/Taipei",
        # United States & US States
        "usa": "America/New_York",
        "us": "America/New_York",
        "united states": "America/New_York",
        "america": "America/New_York",
        "arizona": "America/Phoenix",
        "phoenix": "America/Phoenix",
        "california": "America/Los_Angeles",
        "los angeles": "America/Los_Angeles",
        "la": "America/Los_Angeles",
        "san francisco": "America/Los_Angeles",
        "san diego": "America/Los_Angeles",
        "sacramento": "America/Los_Angeles",
        "washington": "America/Los_Angeles",
        "seattle": "America/Los_Angeles",
        "oregon": "America/Los_Angeles",
        "portland": "America/Los_Angeles",
        "nevada": "America/Los_Angeles",
        "las vegas": "America/Los_Angeles",
        "reno": "America/Los_Angeles",
        "colorado": "America/Denver",
        "denver": "America/Denver",
        "utah": "America/Denver",
        "salt lake city": "America/Denver",
        "new mexico": "America/Denver",
        "albuquerque": "America/Denver",
        "montana": "America/Denver",
        "wyoming": "America/Denver",
        "idaho": "America/Boise",
        "boise": "America/Boise",
        "texas": "America/Chicago",
        "houston": "America/Chicago",
        "dallas": "America/Chicago",
        "austin": "America/Chicago",
        "san antonio": "America/Chicago",
        "illinois": "America/Chicago",
        "chicago": "America/Chicago",
        "minnesota": "America/Chicago",
        "minneapolis": "America/Chicago",
        "wisconsin": "America/Chicago",
        "milwaukee": "America/Chicago",
        "missouri": "America/Chicago",
        "st louis": "America/Chicago",
        "kansas city": "America/Chicago",
        "iowa": "America/Chicago",
        "nebraska": "America/Chicago",
        "omaha": "America/Chicago",
        "kansas": "America/Chicago",
        "oklahoma": "America/Chicago",
        "oklahoma city": "America/Chicago",
        "arkansas": "America/Chicago",
        "louisiana": "America/Chicago",
        "new orleans": "America/Chicago",
        "tennessee": "America/Chicago",
        "nashville": "America/Chicago",
        "memphis": "America/Chicago",
        "alabama": "America/Chicago",
        "mississippi": "America/Chicago",
        "north dakota": "America/Chicago",
        "south dakota": "America/Chicago",
        "new york": "America/New_York",
        "nyc": "America/New_York",
        "florida": "America/New_York",
        "miami": "America/New_York",
        "orlando": "America/New_York",
        "tampa": "America/New_York",
        "georgia": "America/New_York",
        "atlanta": "America/New_York",
        "north carolina": "America/New_York",
        "charlotte": "America/New_York",
        "raleigh": "America/New_York",
        "south carolina": "America/New_York",
        "virginia": "America/New_York",
        "dc": "America/New_York",
        "washington dc": "America/New_York",
        "maryland": "America/New_York",
        "baltimore": "America/New_York",
        "pennsylvania": "America/New_York",
        "philadelphia": "America/New_York",
        "pittsburgh": "America/New_York",
        "new jersey": "America/New_York",
        "connecticut": "America/New_York",
        "massachusetts": "America/New_York",
        "boston": "America/New_York",
        "rhode island": "America/New_York",
        "vermont": "America/New_York",
        "new hampshire": "America/New_York",
        "maine": "America/New_York",
        "ohio": "America/New_York",
        "columbus": "America/New_York",
        "cleveland": "America/New_York",
        "cincinnati": "America/New_York",
        "michigan": "America/Detroit",
        "detroit": "America/Detroit",
        "indiana": "America/Indiana/Indianapolis",
        "indianapolis": "America/Indiana/Indianapolis",
        "kentucky": "America/New_York",
        "louisville": "America/New_York",
        "west virginia": "America/New_York",
        "hawaii": "Pacific/Honolulu",
        "honolulu": "Pacific/Honolulu",
        "alaska": "America/Anchorage",
        "anchorage": "America/Anchorage",
        # Europe & UK
        "london": "Europe/London",
        "uk": "Europe/London",
        "united kingdom": "Europe/London",
        "england": "Europe/London",
        "paris": "Europe/Paris",
        "france": "Europe/Paris",
        "berlin": "Europe/Berlin",
        "germany": "Europe/Berlin",
        "rome": "Europe/Rome",
        "italy": "Europe/Rome",
        "madrid": "Europe/Madrid",
        "spain": "Europe/Madrid",
        "amsterdam": "Europe/Amsterdam",
        "netherlands": "Europe/Amsterdam",
        "zurich": "Europe/Zurich",
        "switzerland": "Europe/Zurich",
        "moscow": "Europe/Moscow",
        "russia": "Europe/Moscow",
        # Middle East & South Asia
        "dubai": "Asia/Dubai",
        "uae": "Asia/Dubai",
        "mumbai": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "india": "Asia/Kolkata",
        # Oceania & Canada
        "sydney": "Australia/Sydney",
        "melbourne": "Australia/Melbourne",
        "australia": "Australia/Sydney",
        "auckland": "Pacific/Auckland",
        "new zealand": "Pacific/Auckland",
        "toronto": "America/Toronto",
        "vancouver": "America/Vancouver",
        "canada": "America/Toronto",
        "cairo": "Africa/Cairo",
        "egypt": "Africa/Cairo",
        "utc": "UTC",
        "gmt": "GMT",
    }

    SAFE_AST_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    @classmethod
    def normalize_currency_code(cls, raw: str) -> Optional[str]:
        if not raw:
            return None
        clean = raw.lower().strip().rstrip(".?!")
        if clean in cls.CURRENCY_ALIASES:
            return cls.CURRENCY_ALIASES[clean]
        upper = clean.upper()
        if upper in cls.OFFLINE_USD_RATES:
            return upper
        return None

    def convert_currency(
        self,
        amount: float,
        from_curr: str,
        to_curr: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Converts currency using Open Exchange Rates API (https://open.er-api.com/v6/latest/{from_curr})
        with deterministic offline fallback rates.
        """
        c_from = self.normalize_currency_code(from_curr) or from_curr.upper().strip()
        c_to = self.normalize_currency_code(to_curr) or to_curr.upper().strip()

        rate = None
        source = "offline_fallback"

        if not dry_run and c_from not in ["BTC", "ETH"] and c_to not in ["BTC", "ETH"]:
            try:
                url = f"https://open.er-api.com/v6/latest/{c_from}"
                resp = requests.get(url, timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    rates = data.get("rates", {})
                    if c_to in rates:
                        rate = float(rates[c_to])
                        source = "open_er_api"
            except Exception:
                pass

        if rate is None:
            r_from = self.OFFLINE_USD_RATES.get(c_from)
            r_to = self.OFFLINE_USD_RATES.get(c_to)
            if r_from and r_to:
                rate = r_to / r_from
            else:
                return {
                    "status": "error",
                    "sub_action": "currency",
                    "voice_response": f"I don't have an exchange rate for {c_from} to {c_to}.",
                }

        converted = round(amount * rate, 2)
        amt_str = f"{int(amount)}" if amount == int(amount) else f"{amount:.2f}"
        conv_str = f"{int(converted)}" if converted == int(converted) else f"{converted:.2f}"
        voice = f"{amt_str} {c_from} is approximately {conv_str} {c_to}."
        return {
            "status": "success",
            "sub_action": "currency",
            "amount": amount,
            "from_currency": c_from,
            "to_currency": c_to,
            "rate": round(rate, 6),
            "converted_amount": converted,
            "source": source,
            "voice_response": voice,
        }

    @classmethod
    def _eval_ast_node(cls, node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return cls._eval_ast_node(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.Num):  # Python <3.8 compatibility
            return float(node.n)
        elif isinstance(node, ast.BinOp) and type(node.op) in cls.SAFE_AST_OPS:
            left = cls._eval_ast_node(node.left)
            right = cls._eval_ast_node(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Exponent too large")
            return float(cls.SAFE_AST_OPS[type(node.op)](left, right))
        elif isinstance(node, ast.UnaryOp) and type(node.op) in cls.SAFE_AST_OPS:
            return float(cls.SAFE_AST_OPS[type(node.op)](cls._eval_ast_node(node.operand)))
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def evaluate_math_or_unit(self, query: str) -> Dict[str, Any]:
        """
        Safely evaluates natural math expressions, percentages, square roots,
        and common unit conversions without using eval().
        """
        q_low = (query or "").lower().strip().rstrip(".?!")

        # 1. Percentage calculation: "25 percent of 1400" / "15% of 680"
        pct_m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:%|percent|pct)\s+of\s+(\d+(?:\.\d+)?)",
            q_low,
        )
        if pct_m:
            pct = float(pct_m.group(1))
            total = float(pct_m.group(2))
            val = (pct / 100.0) * total
            val_fmt = int(val) if val == int(val) else round(val, 4)
            pct_fmt = int(pct) if pct == int(pct) else pct
            tot_fmt = int(total) if total == int(total) else total
            voice = f"{pct_fmt} percent of {tot_fmt} is {val_fmt}."
            return {
                "status": "success",
                "sub_action": "math_unit",
                "result": val_fmt,
                "voice_response": voice,
            }

        # 2. Square root calculation: "square root of 144"
        sqrt_m = re.search(r"square\s+root\s+of\s+(\d+(?:\.\d+)?)", q_low)
        if sqrt_m:
            num = float(sqrt_m.group(1))
            val = math.sqrt(num)
            val_fmt = int(val) if val == int(val) else round(val, 4)
            num_fmt = int(num) if num == int(num) else num
            voice = f"The square root of {num_fmt} is {val_fmt}."
            return {
                "status": "success",
                "sub_action": "math_unit",
                "result": val_fmt,
                "voice_response": voice,
            }

        # 3. Unit conversions: miles<->km, lbs<->kg, fahrenheit<->celsius, feet<->meters, inches<->cm
        unit_m = re.search(
            r"(?:convert\s+|what\s+is\s+|how\s+many\s+)?(\-?\d+(?:\.\d+)?)\s*"
            r"(km|kilometers?|miles?|kg|kilograms?|lbs?|pounds?|celsius|c|fahrenheit|f|inches|inch|cm|centimeters?|feet|foot|ft|meters?|m)"
            r"\s+(?:to|in|into)\s+"
            r"(km|kilometers?|miles?|kg|kilograms?|lbs?|pounds?|celsius|c|fahrenheit|f|inches|inch|cm|centimeters?|feet|foot|ft|meters?|m)\b",
            q_low,
        )
        if unit_m:
            val = float(unit_m.group(1))
            u1 = unit_m.group(2)
            u2 = unit_m.group(3)

            def _norm_unit(u: str) -> str:
                if u in ["km", "kilometer", "kilometers"]:
                    return "km"
                if u in ["mile", "miles"]:
                    return "miles"
                if u in ["kg", "kilogram", "kilograms"]:
                    return "kg"
                if u in ["lb", "lbs", "pound", "pounds"]:
                    return "lbs"
                if u in ["celsius", "c"]:
                    return "celsius"
                if u in ["fahrenheit", "f"]:
                    return "fahrenheit"
                if u in ["inch", "inches"]:
                    return "inches"
                if u in ["cm", "centimeter", "centimeters"]:
                    return "cm"
                if u in ["foot", "feet", "ft"]:
                    return "feet"
                if u in ["meter", "meters", "m"]:
                    return "meters"
                return u

            nu1, nu2 = _norm_unit(u1), _norm_unit(u2)
            res_val = None
            if nu1 == "miles" and nu2 == "km":
                res_val = round(val * 1.60934, 2)
            elif nu1 == "km" and nu2 == "miles":
                res_val = round(val * 0.621371, 2)
            elif nu1 == "lbs" and nu2 == "kg":
                res_val = round(val / 2.20462, 2)
            elif nu1 == "kg" and nu2 == "lbs":
                res_val = round(val * 2.20462, 2)
            elif nu1 == "fahrenheit" and nu2 == "celsius":
                res_val = round((val - 32.0) * 5.0 / 9.0, 2)
            elif nu1 == "celsius" and nu2 == "fahrenheit":
                res_val = round((val * 9.0 / 5.0) + 32.0, 2)
            elif nu1 == "inches" and nu2 == "cm":
                res_val = round(val * 2.54, 2)
            elif nu1 == "cm" and nu2 == "inches":
                res_val = round(val / 2.54, 2)
            elif nu1 == "feet" and nu2 == "meters":
                res_val = round(val * 0.3048, 2)
            elif nu1 == "meters" and nu2 == "feet":
                res_val = round(val / 0.3048, 2)

            if res_val is not None:
                v_in = int(val) if val == int(val) else val
                v_out = int(res_val) if res_val == int(res_val) else res_val
                voice = f"{v_in} {nu1} is {v_out} {nu2}."
                return {
                    "status": "success",
                    "sub_action": "math_unit",
                    "result": v_out,
                    "voice_response": voice,
                }

        # 4. General AST math expression evaluation
        expr = q_low
        expr = re.sub(r"^(?:what\s+is|what's|calculate|compute|evaluate|solve)\s+", "", expr).strip()
        expr = re.sub(r"\bmultiplied\s+by\b|\btimes\b|\bx\b", "*", expr)
        expr = re.sub(r"\bdivided\s+by\b|\bover\b", "/", expr)
        expr = re.sub(r"\bplus\b", "+", expr)
        expr = re.sub(r"\bminus\b", "-", expr)
        expr = re.sub(r"\bto\s+the\s+power\s+of\b|\braised\s+to\b|\^", "**", expr)

        # Keep only valid mathematical tokens
        clean_expr = re.sub(r"[^0-9\.\+\-\*\/\(\)\s]", "", expr).strip()
        if clean_expr and any(op in clean_expr for op in ["+", "-", "*", "/"]):
            try:
                tree = ast.parse(clean_expr, mode="eval")
                ans = self._eval_ast_node(tree)
                ans_fmt = int(ans) if ans == int(ans) else round(ans, 4)
                voice = f"The answer is {ans_fmt}."
                return {
                    "status": "success",
                    "sub_action": "math_unit",
                    "expression": clean_expr,
                    "result": ans_fmt,
                    "voice_response": voice,
                }
            except Exception:
                pass

        return {
            "status": "error",
            "sub_action": "math_unit",
            "voice_response": "I couldn't evaluate that mathematical expression.",
        }

    def get_time_in(self, location: Optional[str] = None, query: str = "") -> Dict[str, Any]:
        """
        Resolves current local time or date in any global timezone using pytz & datetime.
        Defaults to Asia/Kuala_Lumpur.
        """
        tz_name = "Asia/Kuala_Lumpur"
        loc_display = "Kuala Lumpur"

        if location and str(location).strip():
            clean_loc = str(location).lower().strip().rstrip(".?!")
            clean_loc = re.sub(r"\b(?:right\s+now|now|today|currently|please)\b", "", clean_loc).strip()
            if re.search(r"^(?:the\s+)?(?:us|usa|united\s+states|america)[\.\?!]*$", clean_loc, flags=re.IGNORECASE):
                clean_loc = "usa"
            else:
                clean_loc = re.sub(r"^(?:the\s+us\b,?\s*|us\b,?\s*|the\s+united\s+states\b,?\s*|united\s+states\b,?\s*)", "", clean_loc, flags=re.IGNORECASE).strip()
                clean_loc = re.sub(r",?\s*(?:usa|us|united\s+states|america)$", "", clean_loc, flags=re.IGNORECASE).strip()
            if clean_loc in self.TIMEZONE_MAP:
                tz_name = self.TIMEZONE_MAP[clean_loc]
                loc_display = clean_loc.title()
            else:
                # Search pytz timezones by city suffix
                token = clean_loc.replace(" ", "_")
                for z in pytz.all_timezones:
                    if z.lower().endswith(f"/{token}") or token in z.lower():
                        tz_name = z
                        loc_display = clean_loc.title()
                        break

        tz = pytz.timezone(tz_name)
        now_dt = datetime.now(tz)
        q_low = (query or "").lower()

        if ("date" in q_low or "day" in q_low) and "time" not in q_low:
            spoken = f"Today in {loc_display} is {now_dt.strftime('%A, %B %d, %Y')}."
        else:
            time_str = now_dt.strftime("%I:%M %p").lstrip("0")
            date_str = now_dt.strftime("%A, %B %d")
            if location and str(location).strip():
                spoken = f"In {loc_display}, it is currently {time_str} on {date_str}."
            else:
                spoken = f"It is currently {time_str} on {date_str}."

        return {
            "status": "success",
            "sub_action": "time_date",
            "location": loc_display,
            "timezone": tz_name,
            "iso_time": now_dt.isoformat(),
            "voice_response": spoken,
        }

    def check_network_ping(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Checks local IP address and measures internet connectivity & ping latency
        to 1.1.1.1 / 8.8.8.8.
        """
        local_ip = "127.0.0.1"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                local_ip = "127.0.0.1"

        if dry_run:
            return {
                "status": "online",
                "sub_action": "network_ping",
                "online": True,
                "ping_ms": 14.2,
                "local_ip": local_ip,
                "voice_response": f"Your internet connection is online with a ping of 14.2 milliseconds to Cloudflare DNS. Your local IP address is {local_ip}.",
            }

        ping_ms = None
        for host in [("1.1.1.1", 53), ("8.8.8.8", 53)]:
            try:
                t0 = time.perf_counter()
                with socket.create_connection(host, timeout=1.5):
                    ping_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                break
            except Exception:
                continue

        if ping_ms is not None:
            voice = (
                f"Your internet connection is online with a ping of {ping_ms} milliseconds. "
                f"Your local IP address is {local_ip}."
            )
            return {
                "status": "online",
                "sub_action": "network_ping",
                "online": True,
                "ping_ms": ping_ms,
                "local_ip": local_ip,
                "voice_response": voice,
            }

        return {
            "status": "offline",
            "sub_action": "network_ping",
            "online": False,
            "ping_ms": None,
            "local_ip": local_ip,
            "voice_response": f"You appear to be offline right now. Your local IP address is {local_ip}.",
        }

    def handle_query(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Inspects a natural language query and executes the matching FreeUtilityBelt tool
        (currency, math/unit/percentage, world clock/date, or network/ping/IP).
        Returns None if the query is not a utility request.
        """
        q_low = (query or "").lower().strip()
        if not q_low:
            return None

        # 1. Network / Ping / IP check
        if re.search(
            r"\b(?:check\s+my\s+ping|what\s+is\s+my\s+ping|what's\s+my\s+ping|test\s+my\s+ping|is\s+my\s+internet\s+working|am\s+i\s+online|internet\s+connection|what\s+is\s+my\s+(?:local\s+)?ip(?:\s+address)?|what's\s+my\s+ip)\b",
            q_low,
        ):
            return self.check_network_ping(dry_run=dry_run)

        # 2. Time & Date / World Clock
        time_m = (
            re.search(
                r"\b(?:what\s+time\s+is\s+it|what(?:'s|\s+is)\s+the\s+(?:current\s+)?time|current\s+time|tell\s+me\s+the\s+time|what(?:'s|\s+is)\s+today(?:'s)?\s+date|what\s+day\s+is\s+(?:it\s+)?today|what\s+is\s+the\s+date\s+today)\b(?:\s+(?:in|at|for|there|over\s+there)\s*([a-zA-Z\s]*))?",
                q_low,
            )
            or re.search(r"\b(?:what(?:'s|\s+is)\s+the\s+time|what\s+time\s+is\s+it)\b", q_low)
        )
        if time_m:
            loc = None
            if hasattr(time_m, "group") and time_m.groups() and time_m.group(1):
                raw_loc = time_m.group(1).strip()
                clean_loc = re.sub(r"\b(?:right\s+now|now|today|here|please)\b", "", raw_loc).strip()
                loc = clean_loc or None
            if loc in ["there", "over there"] or (not loc and ("there" in q_low or "over there" in q_low)):
                if context and context.get("city"):
                    loc = context["city"]
                else:
                    loc = None
            elif loc and loc.lower() in ["right now", "now", "today", "here"]:
                loc = None
            return self.get_time_in(location=loc, query=q_low)

        # 3. Currency conversion ("How much is 100 USD in MYR?", "Convert 50 Singapore dollars to ringgit")
        curr_aliases_pattern = "|".join(
            sorted((re.escape(k) for k in self.CURRENCY_ALIASES.keys()), key=len, reverse=True)
        )
        curr_m = re.search(
            rf"(?:how\s+much\s+is\s+|convert\s+|what\s+is\s+)?(\d+(?:\.\d+)?)\s*({curr_aliases_pattern})\s+(?:in|to|into)\s+({curr_aliases_pattern})\b",
            q_low,
        )
        if curr_m:
            amt = float(curr_m.group(1))
            c1 = curr_m.group(2)
            c2 = curr_m.group(3)
            return self.convert_currency(amt, c1, c2, dry_run=dry_run)

        # 4. Math, Percentage, Square Root, or Unit Conversion
        if (
            re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent|pct)\s+of\s+(\d+(?:\.\d+)?)", q_low)
            or re.search(r"square\s+root\s+of\s+\d+", q_low)
            or re.search(
                r"\b\d+(?:\.\d+)?\s*(?:km|kilometers?|miles?|kg|kilograms?|lbs?|pounds?|celsius|fahrenheit|inches|inch|cm|feet|foot|meters?)\s+(?:to|in|into)\s+",
                q_low,
            )
            or re.search(
                r"^(?:what\s+is|what's|calculate|compute|evaluate|solve)\s+\d+(?:\.\d+)?\s*(?:\+|\-|\*|\/|plus|minus|times|multiplied\s+by|divided\s+by|to\s+the\s+power\s+of|\^)\s*\d+",
                q_low,
            )
        ):
            res = self.evaluate_math_or_unit(query)
            if res.get("status") == "success":
                return res

        return None
