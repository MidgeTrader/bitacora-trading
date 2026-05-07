import csv
import collections
import datetime
import json
import calendar
import os
import math
import stat
import base64

# Cargar .env si existe
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        # Ensure restrictive permissions (owner read/write only)
        try:
            os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()

# Directory Configuration (Now dynamic based on script location)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = SCRIPT_DIR  # El script esta en la raiz del proyecto

SCHWAB_DIR = os.path.join(BASE_DIR, 'Reports_Schwab')
ALARIC_DIR = os.path.join(BASE_DIR, 'Reports_PropReports')
METATRADER_DIR = os.path.join(BASE_DIR, 'Reports_MetaTrader')
DAS_DIR = os.path.join(BASE_DIR, 'Reports_DAS')
TOS_DIR = os.path.join(BASE_DIR, 'Reports_TOS')
GENERIC_DIR = os.path.join(BASE_DIR, 'Reports_Generic')
GASTOS_DIR = os.path.join(BASE_DIR, 'Reports_Gastos')
OUTPUT_FILE = os.path.join(BASE_DIR, 'trading_report.html')
TAGS_FILE = os.path.join(BASE_DIR, 'tags.json')


def load_tags():
    """Carga asignaciones de tags desde tags.json. Devuelve Dict[str, str]."""
    if os.path.exists(TAGS_FILE):
        try:
            with open(TAGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_tags(tags_dict):
    """Guarda tags a tags.json."""
    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tags_dict, f, indent=2, ensure_ascii=False)


def parse_currency(value):
    if not value or value.strip() == '':
        return 0.0
    clean_val = value.replace('$', '').replace(',', '')
    try:
        return float(clean_val)
    except ValueError:
        return 0.0

def parse_date(date_str):
    try:
        return datetime.datetime.strptime(date_str, '%m/%d/%Y')
    except ValueError:
        return None

def parse_alaric_opened(date_str, weekday_str=''):
    # Prueba formatos DD/MM y MM/DD. Si hay weekday, lo usa para validar.
    all_formats = [
        '%m/%d/%y %H:%M:%S', '%m/%d/%y', # MM/DD/YY (PropReports)
        '%d/%m/%y %H:%M:%S', '%d/%m/%y', # DD/MM/YY
        '%m/%d/%Y %H:%M:%S', '%m/%d/%Y', # MM/DD/YYYY
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y', # DD/MM/YYYY
    ]
    DIAS_SEMANA = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    candidates = []
    for fmt in all_formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            if dt not in candidates:
                candidates.append(dt)
        except ValueError:
            continue
    if not candidates:
        return None
    if weekday_str and len(candidates) > 1:
        expected = weekday_str.strip()
        for dt in candidates:
            if DIAS_SEMANA[dt.weekday()] == expected:
                return dt
    # Sin weekday o sin coincidencia: DD/MM primero
    return candidates[0]

def parse_alaric_closed_candidates(date_str):
    # Returns a list of valid datetime interpretations
    candidates = []
    formats = ['%m/%d/%y %H:%M:%S', '%m/%d/%y', '%d/%m/%y %H:%M:%S', '%d/%m/%y',
               '%m/%d/%Y %H:%M:%S', '%m/%d/%Y', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']
    seen = set()
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            if dt not in seen:
                candidates.append(dt)
                seen.add(dt)
        except ValueError:
            continue
    return candidates

class Trade:
    def __init__(self, date, symbol, quantity, price, action, fees):
        self.date = date
        self.symbol = symbol
        self.quantity = abs(int(quantity)) 
        self.price = price
        self.action = action 
        self.fees = fees

    def __eq__(self, other):
        if not isinstance(other, Trade): return False
        return (self.date, self.symbol, self.quantity, self.price, self.action, self.fees) == \
               (other.date, other.symbol, other.quantity, other.price, other.action, other.fees)

    def __hash__(self):
        return hash((self.date, self.symbol, self.quantity, self.price, self.action, self.fees))

class ClosedTrade:
    def __init__(self, symbol, open_date, close_date, quantity, entry_price, exit_price, entry_fees, exit_fees, direction, tag='', entry_tag='', exit_tag='', note=''):
        self.symbol = symbol
        self.open_date = open_date
        self.close_date = close_date
        self.quantity = quantity
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.entry_fees = entry_fees
        self.exit_fees = exit_fees
        self.direction = direction
        self.tag = tag  # legacy, kept for backwards compat
        self.entry_tag = entry_tag
        self.exit_tag = exit_tag
        self.note = note

        cost_basis = (quantity * entry_price) 
        proceeds = (quantity * exit_price)
        
        total_fees = entry_fees + exit_fees
        
        if direction == 'Long':
            self.gross_pl = proceeds - cost_basis
        else:
            self.gross_pl = cost_basis - proceeds
            
        self.net_pl = self.gross_pl - total_fees
        self.duration = (close_date - open_date).days
        
        if cost_basis > 0:
            self.roi_pct = (self.net_pl / cost_basis) * 100
        else:
            self.roi_pct = 0.0

    @property
    def trade_id(self):
        return f"{self.symbol}|{self.open_date.strftime('%Y-%m-%d %H:%M:%S')}|{self.entry_price}|{self.exit_price}|{self.quantity}"

    def to_dict(self):
        return {
            'symbol': self.symbol,
            'close_date': self.close_date.strftime('%Y-%m-%d'),
            'type': self.direction,
            'quantity': self.quantity,
            'entry': self.entry_price,
            'exit': self.exit_price,
            'pl': self.net_pl,
            'tag': self.entry_tag or self.tag,
            'entry_tag': self.entry_tag,
            'exit_tag': self.exit_tag,
            'note': self.note,
            'trade_id': self.trade_id
        }

    def __eq__(self, other):
        if not isinstance(other, ClosedTrade): return False
        return (self.symbol, self.open_date, self.close_date, self.quantity, self.entry_price, self.exit_price, self.entry_fees, self.exit_fees, self.direction, self.tag, self.entry_tag, self.exit_tag, self.note) == \
               (other.symbol, other.open_date, other.close_date, other.quantity, other.entry_price, other.exit_price, other.entry_fees, other.exit_fees, other.direction, other.tag, other.entry_tag, other.exit_tag, other.note)

    def __hash__(self):
        return hash((self.symbol, self.open_date, self.close_date, self.quantity, self.entry_price, self.exit_price, self.entry_fees, self.exit_fees, self.direction, self.tag, self.entry_tag, self.exit_tag, self.note))

def process_execution_trades(filepath):
    trades = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            data_rows = list(reader)
            data_rows.reverse()
            
            for row in data_rows:
                if row.get('Description', '').startswith('SCHWAB'): continue
                if row.get('Action') not in ['Buy', 'Sell', 'Buy to Cover', 'Sell Short']: continue

                date = parse_date(row['Date'])
                if not date: continue
                
                symbol = row['Symbol']
                qty_str = row['Quantity'].replace(',', '')
                qty = int(qty_str) if qty_str else 0
                price = parse_currency(row['Price'])
                fees = parse_currency(row.get('Fees & Comm', '0'))
                
                action = row['Action'].lower()
                normalized_action = 'Buy'
                if 'sell' in action: normalized_action = 'Sell'
                elif 'buy' in action: normalized_action = 'Buy'

                if not _validate_symbol(symbol) or not _validate_quantity(qty) or not _validate_price(price):
                    continue
                if not _validate_date(date):
                    continue

                trades.append(Trade(date, symbol, qty, price, normalized_action, fees))
                
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return []
    return trades

def process_alaric_trades(filepath):
    trades = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            # Check for header
            first_line = f.readline()
            f.seek(0)
            
            has_header = 'Opened' in first_line and 'Symbol' in first_line
            
            if has_header:
                reader = csv.DictReader(f)
            else:
                # Supply default headers if missing
                fieldnames = ['Opened','Closed','Held','Account','Symbol','Type','CCY','Entry','Exit','Qty','Gross','Comm','Ecn Fee','SECTAF','NSCC','CL','ROR','FPT','FPF','EFT','TTC','ATNET','TAG','Weekday']
                reader = csv.DictReader(f, fieldnames=fieldnames)
                
            # Normalize headers if needed, but assuming they are standard based on inspection
            
            for row in reader:
                if not row.get('Symbol'): continue
                
                # Parse Dates
                open_date = parse_alaric_opened(row.get('Opened', ''), row.get('Weekday', ''))
                
                # Smart Parse Closed Date
                closed_raw = row.get('Closed', '').strip()
                closed_candidates = parse_alaric_closed_candidates(closed_raw)
                close_date = None

                # PropReports exports Closed as HH:MM:SS when same day as Opened
                if open_date and not closed_candidates and closed_raw:
                    for time_fmt in ['%H:%M:%S', '%H:%M']:
                        try:
                            t = datetime.datetime.strptime(closed_raw, time_fmt).time()
                            close_date = datetime.datetime.combine(open_date.date(), t)
                            if close_date < open_date:
                                close_date += datetime.timedelta(days=1)
                            closed_candidates = [close_date]
                            break
                        except ValueError:
                            continue

                if open_date and closed_candidates:
                    # Pick candidate closest to open_date
                    # Filter candidates that are BEFORE open_date (impossible) unless same day/time roughly
                    # Actually, just minimize abs(delta). Ideally close >= open.
                    valid_candidates = [c for c in closed_candidates if c >= open_date - datetime.timedelta(seconds=1)]
                    if not valid_candidates: 
                        # If all are before open, usually data error, but take closest anyway
                        valid_candidates = closed_candidates
                        
                    close_date = min(valid_candidates, key=lambda x: abs(x - open_date))
                elif closed_candidates:
                    close_date = closed_candidates[0] # Fallback if no open date

                if not close_date: continue # Must have close date
                if not open_date: open_date = close_date # Fallback
                
                symbol = row['Symbol']
                
                try:
                    qty = abs(int(float(row.get('Qty', 0))))
                except:
                    qty = 0
                    
                try:
                    entry = float(row.get('Entry', 0))
                    exit_price = float(row.get('Exit', 0))
                except:
                    entry = 0.0
                    exit_price = 0.0
                
                direction = row.get('Type', 'Long') # 'Long' or 'Short'
                
                # Fees Calculation
                # Comm, Ecn Fee, SECTAF, NSCC, CL
                def get_val(key):
                    try: return float(row.get(key, 0))
                    except: return 0.0
                
                fees = 0.0
                fee_cols = ['Comm', 'Ecn Fee', 'SECTAF', 'NSCC', 'CL', 'ROR', 'FPT', 'FPF', 'EFT', 'TTC']
                for col in fee_cols:
                    fees += abs(get_val(col)) # Fees are often negative in this CSV, we want the magnitude
                
                tag = row.get('TAG', '').strip()

                # Validate before creating
                if not _validate_symbol(symbol):
                    print(f"  WARNING: Skipping row with invalid symbol '{symbol}' in {os.path.basename(filepath)}")
                    continue
                if not _validate_quantity(qty):
                    print(f"  WARNING: Skipping row with invalid qty '{qty}' in {os.path.basename(filepath)}")
                    continue
                if not _validate_price(entry) or not _validate_price(exit_price):
                    print(f"  WARNING: Skipping row with invalid price in {os.path.basename(filepath)}")
                    continue
                if not _validate_date(open_date) or not _validate_date(close_date):
                    print(f"  WARNING: Skipping row with invalid date in {os.path.basename(filepath)}")
                    continue

                # ClosedTrade __init__: symbol, open_date, close_date, quantity, entry_price, exit_price, entry_fees, exit_fees, direction, tag
                # We put all fees in 'entry_fees' for simplicity as we don't have the split

                ct = ClosedTrade(symbol, open_date, close_date, qty, entry, exit_price, fees, 0.0, direction, tag)
                trades.append(ct)
                
    except Exception as e:
        print(f"Error reading Alaric CSV: {e}")
        return []

    return trades

# --- CSV Validation ---

def _validate_symbol(symbol):
    """Reject empty, overly long, or suspicious symbols."""
    if not symbol or not isinstance(symbol, str):
        return False
    symbol = symbol.strip()
    if not symbol or len(symbol) > 20:
        return False
    # Must be mostly alphanumeric (allow dots for forex, hyphens for futures)
    return all(c.isalnum() or c in '.-_' for c in symbol)


def _validate_quantity(qty):
    """Quantity must be positive integer within reasonable range."""
    try:
        q = int(float(qty))
    except (ValueError, TypeError):
        return False
    return 1 <= q <= 10_000_000


def _validate_price(price):
    """Price must be non-negative float within reasonable range."""
    try:
        p = float(price)
    except (ValueError, TypeError):
        return False
    return 0.0 <= p <= 10_000_000.0


def _validate_date(dt):
    """Date must be a valid datetime between 2000 and 2100."""
    if dt is None:
        return False
    if not isinstance(dt, datetime.datetime):
        return False
    return datetime.datetime(2000, 1, 1) <= dt <= datetime.datetime(2100, 1, 1)

# --- End Validation ---

def process_metatrader_trades(filepath):
    """Parse MetaTrader 4/5 Account History CSV into ClosedTrade list."""
    trades = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('Item'): continue
                item = row['Item'].strip()
                # MT sometimes exports balance/credit rows — skip non-trading entries
                if item.lower() in ('balance', 'credit', 'deposit', 'withdrawal', 'bonus', 'correction'):
                    continue

                # Parse dates: MT uses "YYYY.MM.DD HH:MM:SS" or "YYYY-MM-DD HH:MM:SS"
                open_date = None
                for fmt in ['%Y.%m.%d %H:%M:%S', '%Y-%m-%d %H:%M:%S',
                            '%Y.%m.%d %H:%M', '%Y-%m-%d %H:%M',
                            '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M']:
                    try:
                        open_date = datetime.datetime.strptime(row.get('Open Time', '').strip(), fmt)
                        break
                    except ValueError:
                        continue

                close_date = None
                for fmt in ['%Y.%m.%d %H:%M:%S', '%Y-%m-%d %H:%M:%S',
                            '%Y.%m.%d %H:%M', '%Y-%m-%d %H:%M',
                            '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M']:
                    try:
                        close_date = datetime.datetime.strptime(row.get('Close Time', '').strip(), fmt)
                        break
                    except ValueError:
                        continue

                if not open_date or not close_date: continue

                symbol = item
                try: qty = abs(int(float(row.get('Size', '0'))))
                except: qty = 0
                if qty == 0: continue

                try: entry = float(row.get('Price', '0'))
                except: entry = 0.0
                try: exit_price = float(row.get('Close Price', '0'))
                except: exit_price = 0.0

                # MT Type field: 'buy' = Long, 'sell' = Short
                mt_type = row.get('Type', '').strip().lower()
                direction = 'Long' if 'buy' in mt_type else 'Short'

                # Fees: Commission + Swap + Taxes
                try: commission = float(row.get('Commission', '0'))
                except: commission = 0.0
                try: swap = float(row.get('Swap', '0'))
                except: swap = 0.0
                try: taxes = float(row.get('Taxes', '0'))
                except: taxes = 0.0
                total_fees = abs(commission) + abs(swap) + abs(taxes)
                # Entry and exit tag from MT Comment (optional)
                mt_tag = row.get('Comment', '').strip()
                if not _validate_symbol(symbol) or not _validate_quantity(qty):
                    continue
                if not _validate_price(entry) or not _validate_price(exit_price):
                    continue
                if not _validate_date(open_date) or not _validate_date(close_date):
                    continue
                ct = ClosedTrade(symbol, open_date, close_date, qty, entry, exit_price,
                                total_fees, 0.0, direction, tag=mt_tag)
                trades.append(ct)
    except Exception as e:
        print(f"Error reading MetaTrader CSV {filepath}: {e}")
        return []
    return trades


def process_das_trades(filepath):
    """Parse DAS Trader execution CSV into Trade list (needs FIFO matching)."""
    trades = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            data_rows = list(reader)
            data_rows.reverse()  # DAS exports most recent first

            for row in data_rows:
                side = row.get('Side', '').strip().upper()
                if not side: continue

                # Parse date: "MM/DD/YYYY" or "YYYY-MM-DD"
                date_str = row.get('Date', '').strip()
                date = None
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%Y']:
                    try:
                        date = datetime.datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if not date: continue

                symbol = row.get('Symbol', '').strip()
                try: qty = int(float(row.get('Quantity', '0')))
                except: qty = 0
                if qty == 0: continue

                try: price = float(row.get('Price', '0'))
                except: price = 0.0

                # DAS fees: check 'Executed' or 'Commission' columns
                fees = 0.0
                for fee_col in ['Commission', 'Executed', 'Fees', 'SEC', 'TAF']:
                    try: fees += abs(float(row.get(fee_col, '0')))
                    except: pass

                # Normalize action
                if 'SHORT' in side and 'SELL' in side:
                    action = 'Sell'
                elif 'SHORT' in side:
                    action = 'Sell'
                elif 'COVER' in side:
                    action = 'Buy'
                elif 'BUY' in side:
                    action = 'Buy'
                elif 'SELL' in side:
                    action = 'Sell'
                else:
                    action = 'Buy' if 'buy' in side.lower() else 'Sell'

                if _validate_symbol(symbol) and _validate_quantity(qty) and _validate_price(price) and _validate_date(date):
                    trades.append(Trade(date, symbol, qty, price, action, fees))
    except Exception as e:
        print(f"Error reading DAS CSV {filepath}: {e}")
        return []
    return trades


def process_tos_trades(filepath):
    """Parse ThinkOrSwim CSV into Trade list (needs FIFO matching)."""
    trades = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            data_rows = list(reader)
            data_rows.reverse()

            for row in data_rows:
                trans = row.get('TRANSACTION', row.get('Transaction', '')).strip()
                if not trans: continue
                trans_upper = trans.upper()

                # Filter: only equity trades
                if any(kw in trans_upper for kw in ['INTEREST', 'DIVIDEND', 'ACH', 'TRANSFER',
                                                      'BALANCE', 'JOURNAL', 'ADJUSTMENT']):
                    continue

                # Parse date: "MM/DD/YYYY"
                date = None
                date_str = row.get('DATE', row.get('Date', '')).strip()
                for fmt in ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d']:
                    try:
                        date = datetime.datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if not date: continue

                symbol = row.get('SYMBOL', row.get('Symbol', '')).strip()
                if not symbol: continue

                try: qty = int(float(row.get('QTY', row.get('Quantity', '0')).replace(',', '')))
                except: qty = 0
                if qty == 0: continue

                try: price = float(row.get('PRICE', row.get('Price', '0')).replace('$', ''))
                except: price = 0.0

                # Fees
                fees = 0.0
                for fee_col in ['COMMISSION/FEE', 'COMMISSION', 'FEES', 'Commission/Fee', 'Comm']:
                    try: fees += abs(float(row.get(fee_col, '0').replace('$', '')))
                    except: pass

                # Normalize action
                if any(kw in trans_upper for kw in ['SELL SHORT', 'SHORT SELL', 'SOLD SHORT']):
                    action = 'Sell'
                elif any(kw in trans_upper for kw in ['BUY TO COVER', 'BOUGHT TO COVER', 'COVER']):
                    action = 'Buy'
                elif 'SELL' in trans_upper:
                    action = 'Sell'
                elif 'BUY' in trans_upper:
                    action = 'Buy'
                else:
                    continue  # Skip unrecognized

                if _validate_symbol(symbol) and _validate_quantity(qty) and _validate_price(price) and _validate_date(date):
                    trades.append(Trade(date, symbol, qty, price, action, fees))
    except Exception as e:
        print(f"Error reading ThinkOrSwim CSV {filepath}: {e}")
        return []
    return trades


def process_generic_trades(filepath):
    """Parse a generic CSV using a mapping.json in the same directory.

    Returns list[Trade] for execution CSVs, list[ClosedTrade] for pre-matched CSVs.
    The mapping.json should look like:
    {
        "type": "executions",
        "date_col": "Date",
        "date_format": "%m/%d/%Y",
        "symbol_col": "Symbol",
        "action_col": "Side",
        "quantity_col": "Qty",
        "price_col": "Price",
        "fees_col": "Commission",
        "net_pl_col": "P&L",
        "buy_values": ["BUY"],
        "sell_values": ["SELL"],
        "direction_col": "Direction",
        "long_values": ["Long", "LONG"],
        "short_values": ["Short", "SHORT"]
    }
    or for matched trades directly:
    {
        "type": "matched",
        "symbol_col": "Symbol",
        "date_format": "%m/%d/%Y",
        ...
    }
    If mapping.json is missing, raises an error suggesting the user create one.
    """
    import json as _json

    dir_path = os.path.dirname(filepath)
    mapping_path = os.path.join(dir_path, 'mapping.json')
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(
            f"No mapping.json found in {dir_path}. Create one to describe your CSV columns. "
            f"See documentation for the format."
        )

    with open(mapping_path, 'r', encoding='utf-8') as mf:
        mapping = _json.load(mf)

    trade_type = mapping.get('type', 'executions')
    date_col = mapping.get('date_col', 'Date')
    date_fmt = mapping.get('date_format', '%m/%d/%Y')
    symbol_col = mapping.get('symbol_col', 'Symbol')
    qty_col = mapping.get('quantity_col', 'Qty')
    price_col = mapping.get('price_col', 'Price')
    fees_col = mapping.get('fees_col', '')

    items = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]

            for row in reader:
                # Parse date
                date_str = row.get(date_col, '').strip()
                date = None
                for fmt in [date_fmt, '%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%Y']:
                    try:
                        date = datetime.datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if not date: continue

                symbol = row.get(symbol_col, '').strip()
                if not symbol: continue

                try: qty = abs(int(float(row.get(qty_col, '0').replace(',', ''))))
                except: qty = 0
                if qty == 0: continue

                try: price = float(row.get(price_col, '0').replace('$', '').replace(',', ''))
                except: price = 0.0

                # Fees
                fees = 0.0
                if fees_col:
                    try: fees = abs(float(row.get(fees_col, '0').replace('$', '').replace(',', '')))
                    except: pass

                if trade_type == 'executions':
                    action_col = mapping.get('action_col', 'Side')
                    raw_action = row.get(action_col, '').strip()
                    buy_vals = mapping.get('buy_values', ['BUY', 'Buy', 'buy'])
                    sell_vals = mapping.get('sell_values', ['SELL', 'Sell', 'sell'])
                    if raw_action in sell_vals:
                        action = 'Sell'
                    else:
                        action = 'Buy'  # default
                    if _validate_symbol(symbol) and _validate_quantity(qty) and _validate_price(price) and _validate_date(date):
                        items.append(Trade(date, symbol, qty, price, action, fees))

                elif trade_type == 'matched':
                    # For pre-matched trades
                    dir_col = mapping.get('direction_col', 'Direction')
                    long_vals = mapping.get('long_values', ['Long', 'LONG'])
                    raw_dir = row.get(dir_col, 'Long').strip()
                    direction = 'Long' if raw_dir in long_vals else 'Short'

                    # Get entry/exit info
                    # Option A: entry=price, exit from net_pl
                    net_pl_col = mapping.get('net_pl_col', '')
                    entry_price = price
                    if net_pl_col:
                        try: net_pl = float(row.get(net_pl_col, '0').replace('$', '').replace(',', ''))
                        except: net_pl = 0.0
                        if direction == 'Long' and qty > 0:
                            exit_price = entry_price + (net_pl / qty)
                        elif qty > 0:
                            exit_price = entry_price - (net_pl / qty)
                        else:
                            exit_price = entry_price
                    else:
                        # Option B: explicit exit_price column
                        exit_col = mapping.get('exit_price_col', '')
                        try: exit_price = float(row.get(exit_col, '0').replace('$', '').replace(',', ''))
                        except: exit_price = entry_price

                    tag = row.get(mapping.get('tag_col', ''), '').strip()
                    if _validate_symbol(symbol) and _validate_quantity(qty) and _validate_price(entry_price) and _validate_date(date):
                        ct = ClosedTrade(symbol, date, date, qty, entry_price, exit_price,
                                        fees, 0.0, direction, tag=tag)
                        items.append(ct)
    except Exception as e:
        print(f"Error reading Generic CSV {filepath}: {e}")
        return []
    return items


def match_trades(trades):
    trades = sorted(trades, key=lambda t: (t.date, t.symbol))
    position_queues = collections.defaultdict(collections.deque)
    closed_trades = []
    
    for t in trades:
        if not position_queues[t.symbol]:
            position_queues[t.symbol].append(t)
            continue
            
        open_lot = position_queues[t.symbol][0]
        is_closing = (open_lot.action != t.action)
        
        if not is_closing:
            position_queues[t.symbol].append(t)
        else:
            qty_remaining_to_close = t.quantity
            current_fees_per_share = t.fees / t.quantity if t.quantity > 0 else 0
            
            while qty_remaining_to_close > 0 and position_queues[t.symbol]:
                lot = position_queues[t.symbol][0]
                qty_matched = min(qty_remaining_to_close, lot.quantity)
                
                if not hasattr(lot, 'unit_fee'):
                    lot.unit_fee = lot.fees / lot.quantity if lot.quantity > 0 else 0
                
                entry_fees = lot.unit_fee * qty_matched
                exit_fees = current_fees_per_share * qty_matched
                
                direction = 'Long' if lot.action == 'Buy' else 'Short'
                entry_price = lot.price
                exit_price = t.price
                
                closed = ClosedTrade(t.symbol, lot.date, t.date, qty_matched, entry_price, exit_price, entry_fees, exit_fees, direction) # No tag for matched trades currently
                closed_trades.append(closed)
                
                qty_remaining_to_close -= qty_matched
                lot.quantity -= qty_matched
                
                if lot.quantity == 0:
                    position_queues[t.symbol].popleft()
            
            if qty_remaining_to_close > 0:
                remainder_fees = current_fees_per_share * qty_remaining_to_close
                remainder_trade = Trade(t.date, t.symbol, qty_remaining_to_close, t.price, t.action, remainder_fees)
                remainder_trade.unit_fee = current_fees_per_share
                position_queues[t.symbol].append(remainder_trade)

    return closed_trades

def _is_date(value, fmt):
    """Return True if value can be parsed with the given strptime format."""
    try:
        datetime.datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False



def process_gastos(filepath):
    # Returns a list of (date_str, category, comment, amount) tuples for detailed deduplication
    expense_items = []
    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as f:
            # Detect if the file has a header row.
            # Header rows start with a non-date string like "Date"; data rows start with a date like "04/01/2026".
            first_line = f.readline().strip()
            f.seek(0)

            first_cell = first_line.split(',')[0].strip()
            first_cell_is_date = any(
                _is_date(first_cell, fmt)
                for fmt in ('%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d')
            )
            has_header = not first_cell_is_date

            if has_header:
                reader = csv.DictReader(f)
            else:
                # No header: columns are Date, Category, Comment, Debit (4 columns)
                reader = csv.DictReader(f, fieldnames=['Date', 'Category', 'Comment', 'Debit'])

            for row in reader:
                try:
                    date_str = row['Date'].strip()
                    if not date_str: continue
                    
                    dt = None
                    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%d/%m/%y'):
                        try:
                            dt = datetime.datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if not dt:
                        print(f"  Warning: Could not parse date '{date_str}' in {filepath}")
                        continue

                    # Ensure we have a reasonable year (if 26 -> 2026)
                    if dt.year < 100:
                        dt = dt.replace(year=dt.year + 2000)
                    elif dt.year < 1900: # Handle cases where %y might be parsed weirdly depending on system
                        if dt.year < 70: dt = dt.replace(year=dt.year + 2000)
                        else: dt = dt.replace(year=dt.year + 1900)

                    key = dt.strftime('%Y-%m-%d')
                    
                    debit_str = row['Debit'].replace(',', '').strip()
                    if not debit_str or float(debit_str) == 0: continue
                    
                    category = row.get('Category', '').strip()
                    comment = row.get('Comment', '').strip()
                    amount = float(debit_str)
                    
                    expense_items.append((key, category, comment, amount))
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        print(f"Warning: Expenses file {filepath} not found.")
    return expense_items

def generate_html_report(closed_trades, expenses_by_day):
    # --- Aggregation Helper ---
    def calculate_kpis(trade_list):
        if not trade_list:
            default_month = {'net_pl': 0.0, 'fees': 0.0, 'count': 0}
            return {
                'gross_pl': 0.0, 'net_pl': 0.0, 'fees': 0.0, 'expenses': 0.0,
                'profit_factor': 0.0, 'win_rate': 0.0, 'total_trades': 0, 'long_count': 0, 'short_count': 0,
                'monthly_breakdown': {i: default_month.copy() for i in range(1, 13)}
            }
        
        net_pl_val = 0.0
        total_fees = 0.0
        wins = []
        losses = []

        # Monthly Accumulators
        monthly_stats = {i: {'net_pl': 0.0, 'fees': 0.0, 'count': 0} for i in range(1, 13)}

        for t in trade_list:
            net_pl_val += t.net_pl
            fees = t.entry_fees + t.exit_fees
            total_fees += fees

            if t.gross_pl > 0: wins.append(t)
            else: losses.append(t)

            
            # Monthly Breakdown
            m_idx = int(t.close_date.month)
            monthly_stats[m_idx]['net_pl'] += t.net_pl
            monthly_stats[m_idx]['fees'] += fees
            monthly_stats[m_idx]['count'] += 1
            
        num_wins = len(wins)
        total_t = len(trade_list)
        
        win_rate_val = (num_wins / total_t) * 100 if total_t > 0 else 0
        gross_wins = sum(t.gross_pl for t in wins)
        gross_losses = sum(t.gross_pl for t in losses)
        profit_factor_val = abs(gross_wins / gross_losses) if losses and gross_losses != 0 else float('inf')
        
        gross_pl_val = net_pl_val + total_fees  # net = gross - fees
        return {
            'gross_pl': gross_pl_val,
            'net_pl': net_pl_val,
            'fees': total_fees,
            'profit_factor': profit_factor_val,
            'win_rate': win_rate_val,
            'total_trades': total_t,
            'long_count': sum(1 for t in trade_list if t.direction == 'Long'),
            'short_count': sum(1 for t in trade_list if t.direction == 'Short'),
            'monthly_breakdown': monthly_stats
        }

    def get_chart_data(trade_list):
        sorted_trades = sorted(trade_list, key=lambda x: x.close_date)
        cum_pl = 0
        peak = -float('inf')
        eq_dates, eq_vals, dd_vals = [], [], []
        m_pl = collections.defaultdict(float)
        
        for t in sorted_trades:
            cum_pl += t.net_pl
            if cum_pl > peak:
                peak = cum_pl
            dd = cum_pl - peak
            
            eq_dates.append(t.close_date.strftime('%m/%y'))
            eq_vals.append(round(cum_pl, 2))
            dd_vals.append(round(dd, 2))
            m_pl[t.close_date.strftime('%Y-%m')] += t.net_pl
            
        sorted_m = sorted(m_pl.keys())
        return {
            'equity': {'labels': eq_dates, 'data': eq_vals},
            'drawdown': {'labels': eq_dates, 'data': dd_vals},
            'monthly': {'labels': sorted_m, 'data': [round(m_pl[m], 2) for m in sorted_m]}
        }

    # Aggregation Helpers (Moved)
    def calculate_gl_stats(trade_list):
        if not trade_list: return {'total_pl': 0.0, 'avg_pl': 0.0, 'avg_pct': 0.0, 'count': 0}
        total_pl = sum(t.gross_pl for t in trade_list)
        count = len(trade_list)
        avg_pl = total_pl / count
        avg_pct = sum(t.roi_pct for t in trade_list) / count
        return {'total_pl': total_pl, 'avg_pl': avg_pl, 'avg_pct': avg_pct, 'count': count}

    def calculate_advanced_stats(trade_list):
        if not trade_list:
            return {
                'expectancy': 0.0, 'max_dd': 0.0, 'max_dd_date': '-',
                'max_consec_wins': 0, 'max_consec_wins_dates': '-',
                'max_consec_losses': 0, 'max_consec_losses_dates': '-',
                'win_loss_ratio': 0.0, 'gain_to_pain': 0.0
            }
        
        # Expectancy
        total_pl = sum(t.gross_pl for t in trade_list)
        count = len(trade_list)
        expectancy = total_pl / count if count > 0 else 0

        # Win/Loss & Gain/Pain
        wins = [t.gross_pl for t in trade_list if t.gross_pl > 0]
        losses = [t.gross_pl for t in trade_list if t.gross_pl <= 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        sum_wins = sum(wins)
        sum_losses = abs(sum(losses))
        
        win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else float('inf')
        gain_to_pain = sum_wins / sum_losses if sum_losses != 0 else float('inf')

        # Advanced Performance Metrics
        win_rate = len(wins) / count if count > 0 else 0
        loss_rate = 1 - win_rate
        edge_score = (win_rate * avg_win) + (loss_rate * avg_loss)
        
        # Kelly Criterion
        payoff_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else 0
        kelly = (win_rate - (1 - win_rate) / payoff_ratio) if payoff_ratio > 0 else 0
        
        # Std Dev and SQN (based on gross P&L)
        pl_values = [t.gross_pl for t in trade_list]
        mean_pl = sum(pl_values) / count if count > 0 else 0
        if count > 1:
            variance = sum((x - mean_pl) ** 2 for x in pl_values) / (count - 1)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0

        sqn = (mean_pl / std_dev) * math.sqrt(count) if std_dev > 0 else 0
        sharpe = (mean_pl / std_dev) if std_dev > 0 else 0 # Simplified Sharpe

        # Sortino Ratio (Downside Deviation)
        downside_returns = [min(0, t.gross_pl) for t in trade_list]
        if count > 1:
            downside_variance = sum(x**2 for x in downside_returns) / count
            downside_std_dev = math.sqrt(downside_variance)
        else:
            downside_std_dev = 0
        sortino = (mean_pl / downside_std_dev) if downside_std_dev > 0 else 0

        # Drawdown & Streaks
        sorted_trades = sorted(trade_list, key=lambda x: x.close_date)
        
        # Max Drawdown
        peak = -float('inf')
        current_cum = 0
        max_dd = 0
        max_dd_date = '-'
        peak_date = None
        max_dd_duration = 0 # Days
        
        # Streaks
        current_streak_type = 0 # 1 win, -1 loss
        current_streak_count = 0
        current_streak_start = None
        
        max_mod_wins = 0
        max_wins_date = '-'
        
        max_mod_losses = 0
        max_losses_date = '-'
        
        # Time Analysis
        win_durations = [t.duration for t in trade_list if t.gross_pl > 0]
        loss_durations = [t.duration for t in trade_list if t.gross_pl <= 0]
        avg_time_win = sum(win_durations) / len(win_durations) if win_durations else 0
        avg_time_loss = sum(loss_durations) / len(loss_durations) if loss_durations else 0
        
        # Long vs Short
        longs = [t for t in trade_list if t.direction == 'Long']
        shorts = [t for t in trade_list if t.direction == 'Short']
        
        def get_pf(trades):
            w = sum(t.gross_pl for t in trades if t.gross_pl > 0)
            l = abs(sum(t.gross_pl for t in trades if t.gross_pl <= 0))
            return w / l if l > 0 else (float('inf') if w > 0 else 0)

        pf_long = get_pf(longs)
        pf_short = get_pf(shorts)
        wr_long = (sum(1 for t in longs if t.gross_pl > 0) / len(longs) * 100) if longs else 0
        wr_short = (sum(1 for t in shorts if t.gross_pl > 0) / len(shorts) * 100) if shorts else 0

        for i, t in enumerate(sorted_trades):
            # DD
            current_cum += t.gross_pl
            if current_cum > peak:
                peak = current_cum
                peak_date = t.close_date

            dd = current_cum - peak
            if dd < max_dd:
                max_dd = dd
                max_dd_date = t.close_date.strftime('%Y-%m-%d')
                if peak_date:
                    duration = (t.close_date - peak_date).days
                    if duration > max_dd_duration:
                        max_dd_duration = duration

            # Streaks
            is_win = t.gross_pl > 0
            type_val = 1 if is_win else -1
            
            if type_val == current_streak_type:
                current_streak_count += 1
            else:
                # End of streak, check max
                if current_streak_type != 0:
                    end_str = sorted_trades[i-1].close_date.strftime('%m/%d')
                    start_str = current_streak_start.strftime('%m/%d')
                    date_range = f"{start_str}-{end_str}"
                    
                    if current_streak_type == 1:
                        if current_streak_count > max_mod_wins:
                            max_mod_wins = current_streak_count
                            max_wins_date = date_range
                    elif current_streak_type == -1:
                        if current_streak_count > max_mod_losses:
                            max_mod_losses = current_streak_count
                            max_losses_date = date_range
                
                current_streak_type = type_val
                current_streak_count = 1
                current_streak_start = t.close_date
        
        # Final streak check
        if current_streak_count > 0:
            end_str = sorted_trades[-1].close_date.strftime('%m/%d')
            start_str = current_streak_start.strftime('%m/%d')
            date_range = f"{start_str}-{end_str}"
            if current_streak_type == 1:
                if current_streak_count > max_mod_wins:
                    max_mod_wins = current_streak_count
                    max_wins_date = date_range
            elif current_streak_type == -1:
                if current_streak_count > max_mod_losses:
                    max_mod_losses = current_streak_count
                    max_losses_date = date_range

        recovery_factor = total_pl / abs(max_dd) if max_dd != 0 else (float('inf') if total_pl > 0 else 0)
        
        # Calmar Ratio (Simplified: NetPL / MaxDD)
        calmar = recovery_factor # Usually annualized, but here we use total period
        
        # Z-Score (Streaks)
        # WWLLW -> streaks: WW, LL, W -> 3 streaks
        streaks_count = 0
        if sorted_trades:
            streaks_count = 1
            for i in range(1, len(sorted_trades)):
                if (sorted_trades[i].net_pl > 0) != (sorted_trades[i-1].net_pl > 0):
                    streaks_count += 1
        
        n_wins = len(wins)
        if count > 1:
            z_score = (count * (streaks_count - 0.5) - 2 * n_wins * (count - n_wins)) / \
                      ( (2 * n_wins * (count - n_wins) * (2 * n_wins * (count - n_wins) - count)) / (count - 1) )**0.5 \
                      if (2 * n_wins * (count - n_wins) * (2 * n_wins * (count - n_wins) - count)) > 0 else 0
        else:
            z_score = 0
            
        # Standard Error & T-Score
        standard_error = std_dev / math.sqrt(count) if count > 0 else 0
        t_score = mean_pl / standard_error if standard_error > 0 else 0
        
        # Trades per Day
        unique_days = set(t.close_date.date() for t in trade_list)
        trades_per_day = count / len(unique_days) if unique_days else 0

        # Consistency Ratio (Sharpe-like but often defined as Mean/StdDev)
        consistency_ratio = sharpe # In this context, they are often used interchangeably

        return {
            'expectancy': expectancy,
            'max_dd': max_dd,
            'max_dd_date': max_dd_date,
            'max_dd_duration': max_dd_duration,
            'recovery_factor': recovery_factor,
            'calmar': calmar,
            'z_score': z_score,
            'equity_peak': peak,
            'trades_per_day': trades_per_day,
            'standard_error': standard_error,
            't_score': t_score,
            'edge_score': edge_score,
            'payoff_ratio': payoff_ratio,
            'sqn': sqn,
            'sharpe': sharpe,
            'sortino': sortino,
            'consistency_ratio': consistency_ratio,
            'kelly': kelly * 100,
            'std_dev': std_dev,
            'avg_time_win': avg_time_win,
            'pf_long': pf_long,
            'pf_short': pf_short,
            'wr_long': wr_long,
            'wr_short': wr_short,
            'max_consec_wins': max_mod_wins,
            'max_consec_wins_dates': max_wins_date,
            'max_consec_losses': max_mod_losses,
            'max_consec_losses_dates': max_losses_date,
            'win_loss_ratio': win_loss_ratio,
            'gain_to_pain': gain_to_pain,
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }

    # --- Annual Data Aggregation ---
    trades_by_year = collections.defaultdict(list)
    for t in closed_trades:
        trades_by_year[t.close_date.strftime('%Y')].append(t)
        
    # --- Annual Data Aggregation ---
    trades_by_year = collections.defaultdict(list)
    for t in closed_trades:
        trades_by_year[t.close_date.strftime('%Y')].append(t)

    years = sorted(trades_by_year.keys())

    # Sum expenses by year
    expenses_by_year = collections.defaultdict(float)
    for date_str, cost in expenses_by_day.items():
        year = date_str[:4]
        expenses_by_year[year] += cost

    # Global Stats & Charts
    annual_stats = {}
    annual_charts = {}

    # "All"
    all_stats = calculate_kpis(closed_trades)
    all_stats['expenses'] = sum(expenses_by_year.values())
    annual_stats['All'] = all_stats
    annual_charts['All'] = get_chart_data(closed_trades)

    # Years
    for y in years:
        year_stats = calculate_kpis(trades_by_year[y])
        year_stats['expenses'] = expenses_by_year.get(y, 0.0)
        annual_stats[y] = year_stats
        annual_charts[y] = get_chart_data(trades_by_year[y])

    # JSON Serialization
    annual_stats_json = json.dumps(annual_stats)
    annual_charts_json = json.dumps(annual_charts)
    available_years_json = json.dumps(['All'] + years)

    # Tags data for interactive editor (trade_id -> {entry_tag, exit_tag, note})
    all_tags_data = {}
    for t in closed_trades:
        if t.entry_tag or t.exit_tag or t.note:
            all_tags_data[t.trade_id] = {
                'entry_tag': t.entry_tag,
                'exit_tag': t.exit_tag,
                'note': t.note
            }
    daily_tags_json = json.dumps(all_tags_data)

    # --- Daily Data Aggregation ---
    trades_by_day = collections.defaultdict(list)
    for t in closed_trades:
        trades_by_day[t.close_date.strftime('%Y-%m-%d')].append(t)

    daily_stats = {}
    for d_key, trades in trades_by_day.items():
        wins = [t for t in trades if t.net_pl > 0]
        losses = [t for t in trades if t.net_pl <= 0]
        total_fees = sum(t.entry_fees + t.exit_fees for t in trades)
        
        stats_all = calculate_gl_stats(trades)
        stats_won = calculate_gl_stats(wins)
        stats_lost = calculate_gl_stats(losses)
        stats_adv = calculate_advanced_stats(trades)
        
        daily_stats[d_key] = {
            'pnl': sum(t.net_pl for t in trades),
            'count': len(trades),
            'fees': total_fees,
            'trades': [t.to_dict() for t in trades],
            'stats': {
                'all': stats_all,
                'won': stats_won,
                'lost': stats_lost,
                'advanced': stats_adv
            }

        }
    
    # Merge Expenses into Daily Stats
    for d_key, cost in expenses_by_day.items():
        if d_key not in daily_stats:
            daily_stats[d_key] = {
                'pnl': 0.0, 'count': 0, 'fees': 0.0, 'trades': [],
                'stats': {'all': {}, 'won': {}, 'lost': {}, 'advanced': {}} # Empty stats
            }
        
        daily_stats[d_key]['fees'] += cost
        # Excluded from P&L per user request to avoid distorting charts
        # daily_stats[d_key]['pnl'] -= cost 

    # Monthly/Daily Context (Equity Curves etc)
    monthly_pl = collections.defaultdict(float)
    monthly_equity_curves = collections.defaultdict(lambda: {'labels': [], 'data': []})
    daily_equity_curves = collections.defaultdict(lambda: {'labels': [], 'data': []})
    
    current_month_pl = collections.defaultdict(float)
    current_day_pl = collections.defaultdict(float)
    
    # Needs chronological for equity curves
    closed_trades.sort(key=lambda x: x.close_date) 
    
    for t in closed_trades:
        m_key = t.close_date.strftime('%Y-%m')
        d_key = t.close_date.strftime('%Y-%m-%d')
        
        monthly_pl[m_key] += t.net_pl
        
        current_month_pl[m_key] += t.net_pl
        monthly_equity_curves[m_key]['labels'].append(t.close_date.strftime('%d/%b'))
        monthly_equity_curves[m_key]['data'].append(round(current_month_pl[m_key], 2))
        
        current_day_pl[d_key] += t.net_pl
        daily_equity_curves[d_key]['labels'].append('')
        daily_equity_curves[d_key]['data'].append(round(current_day_pl[d_key], 2))

    # Incorporate expenses into Monthly PL and Monthly Equity
    # Note: Equity curves above were built trade-by-trade. Expenses are day-level. 
    # Ideally, we sort expenses and trades together. 
    # Quick fix: Adjust monthly_pl sums. (Equity curves might slightly mismatch intraday if cost was 'at start', but acceptable).
    # Excluded from P&L per user request to avoid distorting charts
    # for d_key, cost in expenses_by_day.items():
    #     m_key = d_key[:7] # YYYY-MM
    #     monthly_pl[m_key] -= cost

    monthly_equity_json = json.dumps(monthly_equity_curves)
    daily_equity_json = json.dumps(daily_equity_curves)
    daily_data_json = json.dumps(daily_stats)
    monthly_data_json = json.dumps(monthly_pl)
    
    # Monthly Symbols & Context Stats
    monthly_symbols = collections.defaultdict(lambda: collections.defaultdict(lambda: {'pnl': 0.0, 'count': 0}))
    for t in closed_trades:
        m_key = t.close_date.strftime('%Y-%m')
        monthly_symbols[m_key][t.symbol]['pnl'] += t.net_pl
        monthly_symbols[m_key][t.symbol]['count'] += 1
        
    monthly_symbols_list = {}
    for m_key, sym_dict in monthly_symbols.items():
        s_list = [{'symbol': s, 'pnl': d['pnl'], 'count': d['count']} for s, d in sym_dict.items()]
        s_list.sort(key=lambda x: x['pnl'], reverse=True)
        monthly_symbols_list[m_key] = s_list
    monthly_symbols_json = json.dumps(monthly_symbols_list)
    
    monthly_context_stats = {}
    monthly_gain_loss_stats = {}

    def calculate_tag_metrics(trade_list):
        tag_dict = collections.defaultdict(list)
        for t in trade_list:
            t_tag = (t.entry_tag or t.tag).strip() if hasattr(t, 'entry_tag') else ''
            if not t_tag:
                tag_dict['Untagged'].append(t)
            else:
                # Split comma-separated tags
                for single_tag in t_tag.split(','):
                    single_tag = single_tag.strip()
                    if single_tag:
                        tag_dict[single_tag].append(t)

        results = []
        for tag, trades in tag_dict.items():
            count = len(trades)
            wins = [t for t in trades if t.net_pl > 0]
            win_rate = (len(wins) / count * 100) if count > 0 else 0
            total_pl = sum(t.net_pl for t in trades)
            avg_pl = total_pl / count if count > 0 else 0
            # Include individual trades for expandable view
            trade_list_data = []
            for t in trades:
                trade_list_data.append({
                    'symbol': t.symbol,
                    'dir': t.direction,
                    'entry': round(t.entry_price, 4),
                    'exit': round(t.exit_price, 4),
                    'qty': t.quantity,
                    'pl': round(t.net_pl, 2),
                    'date': t.close_date.strftime('%Y-%m-%d'),
                    'exit_tag': t.exit_tag if hasattr(t, 'exit_tag') else '',
                    'note': t.note if hasattr(t, 'note') else ''
                })
            # Sort trades by date
            trade_list_data.sort(key=lambda x: x['date'])
            results.append({
                'tag': tag,
                'count': count,
                'win_rate': win_rate,
                'avg_pl': avg_pl,
                'trades': trade_list_data
            })
        results.sort(key=lambda x: x['count'], reverse=True)
        return results

    def calculate_weekday_metrics(trade_list):
        weekday_dict = collections.defaultdict(list)
        # 0=Monday, 6=Sunday
        for t in trade_list:
            wd = t.close_date.weekday()
            weekday_dict[wd].append(t)
        
        results = []
        # Days names mapping
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for wd, trades in weekday_dict.items():
            count = len(trades)
            wins = [t for t in trades if t.net_pl > 0]
            win_rate = (len(wins) / count * 100) if count > 0 else 0
            total_pl = sum(t.net_pl for t in trades)
            avg_pl = total_pl / count if count > 0 else 0
            
            results.append({
                'day_name': days[wd],
                'day_index': wd,
                'count': count,
                'win_rate': win_rate,
                'total_pl': total_pl,
                'avg_pl': avg_pl
            })
            
        # Sort by day index (Monday first)
        results.sort(key=lambda x: x['day_index'])
        return results

    for m_key in monthly_symbols.keys():
        m_trades = [t for t in closed_trades if t.close_date.strftime('%Y-%m') == m_key]
        
        # Context Stats
        stats = calculate_kpis(m_trades)
        monthly_context_stats[m_key] = {
            'win_rate': stats['win_rate'],
            'profit_factor': stats['profit_factor'],
            'total_trades': stats['total_trades'],
            'long_count': stats['long_count'],
            'short_count': stats['short_count'],
            'fees': stats['fees'],
            'avg_win': 0, 'avg_loss': 0 
        }

        # Gain Loss Stats
        gl_stats = calculate_gl_stats(m_trades)
        
        # Expenses
        m_cost = 0.0
        for date_str, cost in expenses_by_day.items():
            if date_str.startswith(m_key):
                m_cost += cost
        
        # Excluded from PL stats below to avoid distortion
        # gl_stats['total_pl'] -= m_cost
        # if gl_stats['count'] > 0:
        #     gl_stats['avg_pl'] = gl_stats['total_pl'] / gl_stats['count']

        unique_days = set(t.close_date.date() for t in m_trades)
        traded_days_count = len(unique_days)
        # Avg Daily P&L now reflects only trading P&L
        avg_daily_pl = gl_stats['total_pl'] / traded_days_count if traded_days_count > 0 else 0.0

        m_wins_sub = [t for t in m_trades if t.net_pl > 0]
        m_losses_sub = [t for t in m_trades if t.net_pl <= 0]
        
        monthly_gain_loss_stats[m_key] = {
            'all': gl_stats,
            'won': calculate_gl_stats(m_wins_sub),
            'lost': calculate_gl_stats(m_losses_sub),
            'advanced': calculate_advanced_stats(m_trades),
            'tags': calculate_tag_metrics(m_trades),
            'weekdays': calculate_weekday_metrics(m_trades),
            'expenses': m_cost,
            'traded_days': traded_days_count,
            'avg_daily_pl': avg_daily_pl
        }

    monthly_stats_json = json.dumps(monthly_context_stats)
    monthly_gain_loss_json = json.dumps(monthly_gain_loss_stats)

    print(f"DEBUG: Annual Stats Keys: {annual_stats.keys()}")
    if 'All' in annual_stats:
        print(f"DEBUG: All Net PL: {annual_stats['All']['net_pl']}")

    # Embed logo as base64
    logo_b64 = ""
    logo_path = os.environ.get("LOGO_PATH", os.path.join(os.path.dirname(__file__), "logo.png"))
    try:
        with open(logo_path, "rb") as lf:
            logo_b64 = base64.b64encode(lf.read()).decode()
    except FileNotFoundError:
        pass

    # --- HTML Generator ---

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{os.environ.get('TRADER_NAME', 'Trading Report')}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700&family=Rajdhani:wght@300;400;500;600;700&family=Space+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #030712;
            --card-bg: rgba(3, 7, 18, 0.7);
            --text-primary: #e2e8f0;
            --text-secondary: #94a3b8;
            --accent-primary: #00d4ff; 
            --accent-primary-dim: rgba(0, 212, 255, 0.15);
            --accent-green: #39ff14; 
            --accent-red: #ff003c; 
            --accent-blue: #00d4ff;
            --border-color: rgba(0, 212, 255, 0.3);
            --border-glow: 0 0 10px rgba(0, 212, 255, 0.2), inset 0 0 10px rgba(0, 212, 255, 0.1);
            --hover-bg: rgba(0, 212, 255, 0.1);
        }}
        
        /* Layout & HUD Background */
        body {{ 
            display: flex; overflow: hidden; height: 100vh; margin: 0; 
            font-family: 'Rajdhani', sans-serif; 
            background-color: var(--bg-color); 
            color: var(--text-primary);
            transition: background-color 0.3s ease;
        }}
        
        /* Circuit Background Canvas */
        #circuit-bg {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
            transition: opacity 0.3s;
        }}
        
        h1, h2, h3, .card-title {{
            font-family: 'Orbitron', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }}

        .sidebar {{
            width: 260px;
            background-color: rgba(3, 7, 18, 0.85);
            backdrop-filter: blur(12px);
            border-right: 1px solid var(--border-color);
            box-shadow: 2px 0 15px rgba(0, 212, 255, 0.1);
            display: flex; flex-direction: column;
            padding: 1.5rem;
            flex-shrink: 0;
            z-index: 10;
        }}
        .main-content {{
            flex-grow: 1;
            padding: 2rem;
            overflow-y: auto;
            position: relative;
        }}
        
        /* Custom Scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: rgba(0,0,0,0.2); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border-color); border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--accent-primary); }}

        .nav-btn {{
            background: transparent;
            border: 1px solid transparent;
            border-left: 3px solid transparent;
            color: var(--text-secondary);
            text-align: left;
            padding: 0.8rem 1rem;
            border-radius: 0;
            cursor: pointer;
            font-size: 1rem;
            font-family: 'Orbitron', sans-serif;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        .nav-btn::before {{
            content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(90deg, var(--accent-primary-dim), transparent);
            transform: translateX(-100%); transition: transform 0.3s ease; z-index: -1;
        }}
        .nav-btn:hover::before {{ transform: translateX(0); }}
        .nav-btn:hover {{ color: var(--accent-primary); border-left-color: var(--accent-primary); text-shadow: 0 0 8px var(--accent-primary); }}
        .nav-btn.active {{ 
            background: var(--accent-primary-dim); 
            color: var(--accent-primary); 
            border-left: 3px solid var(--accent-primary);
            text-shadow: 0 0 8px var(--accent-primary);
            box-shadow: inset 10px 0 20px -10px var(--accent-primary);
        }}
        
        .view-section {{ display: none; animation: hudFadeIn 0.4s ease-out forwards; opacity: 0; transform: scale(0.98); }}
        .view-section.active {{ display: block; }}
        @keyframes fadeOut {{ 0% {{ opacity:1; }} 80% {{ opacity:1; }} 100% {{ opacity:0; }} }}
        @keyframes hudFadeIn {{
            0% {{ opacity: 0; transform: scale(0.98) translateY(10px); filter: blur(4px); }} 
            100% {{ opacity: 1; transform: scale(1) translateY(0); filter: blur(0); }} 
        }}

        /* HUD Components */
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
        
        .card {{ 
            background-color: var(--card-bg); 
            backdrop-filter: blur(10px);
            border-radius: 4px; 
            padding: 1.5rem; 
            border: 1px solid var(--border-color); 
            box-shadow: var(--border-glow);
            position: relative;
            overflow: hidden;
        }}
        /* HUD Corner Accents */
        .card::before, .card::after {{
            content: ''; position: absolute; width: 10px; height: 10px; border: 2px solid var(--accent-primary); transition: all 0.3s;
        }}
        .card::before {{ top: -1px; left: -1px; border-right: none; border-bottom: none; }}
        .card::after {{ bottom: -1px; right: -1px; border-left: none; border-top: none; }}
        .card:hover::before, .card:hover::after {{ width: 20px; height: 20px; box-shadow: 0 0 10px var(--accent-primary); }}

        /* Laser scan bar effect on hover */
        .laser-bar {{
            position: absolute;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--accent-primary), transparent);
            box-shadow: 0 0 8px var(--accent-primary), 0 0 20px rgba(0, 212, 255, 0.4);
            top: 0;
            animation: laserBarDown 0.6s ease-in-out forwards;
            pointer-events: none;
            z-index: 5;
        }}
        @keyframes laserBarDown {{
            0% {{ top: 0; opacity: 0; }}
            5% {{ opacity: 1; }}
            85% {{ opacity: 1; }}
            100% {{ top: 100%; opacity: 0; }}
        }}

        .card-title {{ 
            color: var(--accent-primary); 
            font-size: 0.7rem; 
            margin-bottom: 0.75rem; 
            text-shadow: 0 0 5px rgba(0, 212, 255, 0.5);
        }}
        .card-value {{ 
            font-family: 'Space Mono', monospace;
            font-size: 1.75rem; 
            font-weight: 700; 
            color: #fff;
            text-shadow: 0 0 10px rgba(255,255,255,0.3);
        }}
        .positive {{ color: var(--accent-green) !important; text-shadow: 0 0 10px rgba(57, 255, 20, 0.4) !important; }}
        .negative {{ color: var(--accent-red) !important; text-shadow: 0 0 10px rgba(255, 0, 60, 0.4) !important; }}
        
        .charts-section {{ display: grid; grid-template-columns: 2fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
        .chart-container {{ position: relative; height: 350px; width: 100%; }}
        
        table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.9rem; }}
        th, td {{ padding: 0.85rem; border-bottom: 1px solid rgba(0, 212, 255, 0.15); }}
        th {{ 
            color: var(--accent-primary); 
            font-family: 'Orbitron', sans-serif;
            font-size: 0.7rem;
            letter-spacing: 0.1em;
            text-transform: uppercase; 
            background: rgba(0, 212, 255, 0.05);
        }}
        tr:hover td {{ background-color: rgba(0, 212, 255, 0.05); }}
        
        /* Annual Grid */
        .annual-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.5rem; }}
        .month-card {{ 
            background-color: var(--card-bg); 
            border: 1px solid var(--border-color); 
            border-radius: 4px; 
            padding: 1.5rem; 
            cursor: pointer; 
            transition: all 0.2s; 
            box-shadow: var(--border-glow);
            position: relative;
            overflow: hidden;
        }}
        .month-card:hover {{ 
            transform: translateY(-2px); 
            border-color: var(--accent-primary);
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.3), inset 0 0 15px rgba(0, 212, 255, 0.1);
        }}
        /* Scanline effect on hover */
        .month-card::after {{
            content: ''; position: absolute; top: -100%; left: 0; width: 100%; height: 50%;
            background: linear-gradient(to bottom, transparent, rgba(0, 212, 255, 0.2), transparent);
            transition: 0s;
        }}
        .month-card:hover::after {{ animation: scanline 1.5s linear infinite; }}
        @keyframes scanline {{ 0% {{ top: -50%; }} 100% {{ top: 150%; }} }}

        /* Calendar */
        .calendar-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .calendar-nav-btn {{ 
            background: transparent; 
            border: 1px solid var(--accent-primary); 
            color: var(--accent-primary); 
            padding: 0.4rem 1.2rem; 
            cursor: pointer; 
            border-radius: 2px;
            font-family: 'Orbitron', sans-serif;
            font-size: 0.75rem;
            text-transform: uppercase;
            box-shadow: 0 0 8px rgba(0, 212, 255, 0.2);
            transition: all 0.2s;
        }}
        .calendar-nav-btn:hover {{ 
            background: var(--accent-primary); 
            color: #000;
            box-shadow: 0 0 15px var(--accent-primary);
        }}
        .calendar-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.5rem; }}
        .day-name {{ text-align: center; color: var(--accent-primary); font-family: 'Orbitron', sans-serif; font-size: 0.7rem; padding: 0.5rem; letter-spacing: 0.1em; text-transform: uppercase; }}
        .day-cell {{ 
            background-color: rgba(15, 23, 42, 0.6); 
            border-radius: 2px; 
            min-height: 55px; 
            padding: 0.5rem; 
            display: flex; flex-direction: column; justify-content: space-between; 
            cursor: pointer; 
            border: 1px solid rgba(0, 212, 255, 0.1); 
            transition: all 0.2s;
        }}
        .day-cell:hover {{ border-color: var(--accent-primary); box-shadow: 0 0 10px rgba(0, 212, 255, 0.3); transform: scale(1.02); z-index: 2; }}
        .day-cell.empty {{ background: transparent; border: 1px dashed rgba(0, 212, 255, 0.1); cursor: default; }}
        .day-cell.empty:hover {{ transform: none; box-shadow: none; border-color: rgba(0, 212, 255, 0.1); }}
        .day-number {{ font-family: 'Space Mono', monospace; font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem; }}
        .day-pnl {{ font-family: 'Space Mono', monospace; font-size: 0.95rem; font-weight: 700; text-align: right; }}
        .day-trades {{ font-size: 0.65rem; color: var(--text-secondary); text-align: right; text-transform: uppercase; }}
        .week-total {{ 
            display: flex; flex-direction: column; justify-content: center; 
            background-color: rgba(0, 212, 255, 0.05); 
            border-radius: 2px; padding: 0.5rem; text-align: right; 
            border: 1px solid var(--border-color); 
        }}
        .week-label {{ font-family: 'Orbitron', sans-serif; font-size: 0.65rem; color: var(--accent-primary); text-transform: uppercase; margin-bottom: 0.25rem; letter-spacing: 0.05em; }}
        .bg-green {{ background-color: rgba(57, 255, 20, 0.05); border-color: rgba(57, 255, 20, 0.3); }}
        .bg-green:hover {{ box-shadow: 0 0 15px rgba(57, 255, 20, 0.2); border-color: var(--accent-green); }}
        .bg-red {{ background-color: rgba(255, 0, 60, 0.05); border-color: rgba(255, 0, 60, 0.3); }}
        .bg-red:hover {{ box-shadow: 0 0 15px rgba(255, 0, 60, 0.2); border-color: var(--accent-red); }}

        /* ===== BUILD REPORT TAB ===== */
        .build-report-layout {{ display: flex; flex-direction: column; gap: 1.5rem; }}
        .br-filters-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
        .br-panel {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 1.25rem; box-shadow: var(--border-glow); }}
        .br-panel-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; font-family: 'Orbitron', sans-serif; font-size: 0.85rem; color: var(--accent-primary); text-transform: uppercase; letter-spacing: 0.05em; }}
        .br-panel-header .count {{ color: var(--accent-green); font-size: 0.9rem; }}
        .br-panel-label {{ font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; font-family: 'Orbitron', sans-serif; }}
        .br-input, .br-select {{ width: 100%; padding: 0.5rem 0.75rem; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-family: 'Rajdhani', sans-serif; font-size: 0.9rem; outline: none; transition: border-color 0.2s; }}
        .br-input:focus, .br-select:focus {{ border-color: var(--accent-primary); box-shadow: 0 0 8px rgba(0,212,255,0.2); }}
        .br-select option {{ background: #030712; color: var(--text-primary); }}
        .br-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem; }}
        .br-actions {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; padding-right: 160px; }}
        .br-actions-center {{ flex: 1; display: flex; justify-content: center; gap: 0.75rem; }}
        .br-btn {{ padding: 0.6rem 1.5rem; border-radius: 6px; font-family: 'Orbitron', sans-serif; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; cursor: pointer; border: 1px solid var(--border-color); transition: all 0.3s; }}
        .br-btn-primary {{ background: var(--accent-primary); color: #000; border-color: var(--accent-primary); font-weight: 600; }}
        .br-btn-primary:hover {{ box-shadow: 0 0 15px rgba(0,212,255,0.4); }}
        .br-btn-secondary {{ background: transparent; color: var(--text-secondary); border-color: var(--border-color); }}
        .br-btn-secondary:hover {{ color: var(--accent-primary); border-color: var(--accent-primary); }}
        .br-section-title {{ font-family: 'Orbitron', sans-serif; font-size: 0.85rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem; }}
        .br-empty {{ text-align: center; padding: 3rem; color: var(--text-secondary); font-size: 1rem; border: 1px dashed var(--border-color); border-radius: 12px; }}
        .br-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 0.5rem; }}
        .br-table th {{ text-align: left; padding: 0.75rem 1rem; font-family: 'Orbitron', sans-serif; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); }}
        .br-table td {{ padding: 0.65rem 1rem; border-bottom: 1px solid rgba(0,212,255,0.1); }}
        .br-table tr:last-child td {{ border-bottom: none; }}
        .br-table .metric-name {{ font-weight: 500; color: var(--text-primary); }}
        .br-table .value-a, .br-table .value-b {{ color: var(--accent-primary); font-weight: 600; }}
        .br-badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.65rem; font-weight: 600; margin-left: 0.5rem; }}
        .br-badge-a {{ background: rgba(0,212,255,0.15); color: var(--accent-primary); }}
        .br-badge-b {{ background: rgba(57,255,20,0.15); color: var(--accent-green); }}
        .br-tag-select {{ display: flex; flex-wrap: wrap; gap: 0.3rem; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 6px; padding: 0.4rem; min-height: 38px; cursor: pointer; }}
        .br-tag-select:hover {{ border-color: var(--accent-primary); }}
        .br-tag-chip {{ display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.15rem 0.5rem; border-radius: 10px; background: rgba(0,212,255,0.15); color: var(--accent-primary); font-size: 0.75rem; }}
        .br-tag-chip .remove {{ cursor: pointer; opacity: 0.7; margin-left: 0.15rem; }}
        .br-tag-chip .remove:hover {{ opacity: 1; }}
        .br-tag-dropdown {{ position: absolute; top: 100%; left: 0; right: 0; background: rgba(3,7,18,0.98); border: 1px solid var(--border-color); border-radius: 6px; max-height: 180px; overflow-y: auto; z-index: 50; display: none; }}
        .br-tag-dropdown.show {{ display: block; }}
        .br-tag-option {{ padding: 0.4rem 0.75rem; cursor: pointer; font-size: 0.85rem; transition: background 0.2s; }}
        .br-tag-option:hover {{ background: var(--hover-bg); color: var(--accent-primary); }}
        .br-tag-wrap {{ position: relative; }}
        .br-no-data {{ text-align: center; padding: 2rem; color: var(--text-secondary); font-style: italic; }}
        .br-metric-hdr {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); font-family: 'Orbitron', sans-serif; padding-bottom: 0.25rem; }}

        @media (max-width: 768px) {{
            .br-filters-container {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <canvas id="circuit-bg"></canvas>
    <aside class="sidebar" style="position: relative; z-index: 10;">
        <div style="margin-bottom: 2rem; text-align: center;">
            <img src="data:image/png;base64,{logo_b64}" style="width: 150px; height: 150px; object-fit: cover; border-radius: 50%; border: 2px solid var(--accent-primary); box-shadow: 0 0 15px var(--accent-primary); margin-bottom: 1rem;">
            <h2 style="margin:0; font-size:1.8rem; text-transform: none; background: linear-gradient(to right, #60a5fa, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(5px 5px 0px rgba(255, 255, 255, 0.15));">{os.environ.get('TRADER_NAME', 'Trading Report')}</h2>
            <p style="font-size: 1.2rem; color: #40E0D0; font-weight: 600;">Performance</p>
        </div>
        <button class="nav-btn active" onclick="switchView('annual')" id="btn-annual">Annual Board</button>
        <button class="nav-btn" onclick="switchView('monthly')" id="btn-monthly">Calendar</button>
        <button class="nav-btn" onclick="switchView('daily')" id="btn-daily">Daily details</button>
        <button class="nav-btn" onclick="switchView('ratios')" id="btn-ratios">Metricas</button>
        <button class="nav-btn" onclick="switchView('buildReport')" id="btn-buildReport">&#x1F4CA; Build Report</button>
    </aside>

    <main class="main-content" style="position: relative; z-index: 10;">
        <!-- CUSTOMIZATION TRIGGER -->
        <button id="customizationTrigger" onclick="toggleCustomizer()" style="position: absolute; top: 1.5rem; right: 2rem; background: var(--card-bg); border: 1px solid var(--border-color); color: var(--accent-primary); padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', sans-serif; font-size: 0.7rem; z-index: 100; box-shadow: var(--border-glow); display: flex; align-items: center; gap: 0.5rem; transition: all 0.3s;">
            <span style="font-size: 1rem;">🎨</span> CUSTOMIZE
        </button>

        <!-- CUSTOMIZATION SIDEBAR -->
        <div id="customizerSidebar" style="position: fixed; top: 0; right: -400px; width: 350px; height: 100vh; background: rgba(3, 7, 18, 0.95); backdrop-filter: blur(25px); border-left: 1px solid var(--border-color); z-index: 1000; transition: right 0.4s cubic-bezier(0.4, 0, 0.2, 1); padding: 2rem; overflow-y: auto; box-shadow: -10px 0 30px rgba(0,0,0,0.5);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2.5rem;">
                <h2 style="margin: 0; font-size: 1.2rem; color: var(--accent-primary); letter-spacing: 2px;">THEME CONFIG</h2>
                <button onclick="toggleCustomizer()" style="background: transparent; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.5rem; transition: color 0.2s;">&times;</button>
            </div>

            <div style="margin-bottom: 2rem;">
                <div class="card-title" style="margin-bottom: 1rem;">Quick Presets</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem;">
                    <button class="nav-btn" style="font-size: 0.6rem; margin: 0; padding: 0.5rem;" onclick="applyPreset('#00d4ff')">Tron Cyan</button>
                    <button class="nav-btn" style="font-size: 0.6rem; margin: 0; padding: 0.5rem;" onclick="applyPreset('#39ff14')">Matrix</button>
                    <button class="nav-btn" style="font-size: 0.6rem; margin: 0; padding: 0.5rem;" onclick="applyPreset('#ff003c')">Red Alert</button>
                    <button class="nav-btn" style="font-size: 0.6rem; margin: 0; padding: 0.5rem;" onclick="applyPreset('#a855f7')">Purple Rain</button>
                    <button class="nav-btn" style="font-size: 0.6rem; margin: 0; padding: 0.5rem;" onclick="applyPreset('#f59e0b')">Gold Ember</button>
                    <button class="nav-btn" style="font-size: 0.6rem; margin: 0; padding: 0.5rem;" onclick="applyPreset('#e2e8f0')">Mono Steel</button>
                </div>
            </div>

            <div style="margin-bottom: 2rem;">
                <div class="card-title" style="margin-bottom: 1rem;">Primary Accent</div>
                <div style="display: flex; align-items: center; gap: 1rem; background: var(--card-bg); padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 4px;">
                    <input type="color" id="accentPicker" value="#00d4ff" oninput="updateAccent(this.value)" style="background: none; border: none; width: 40px; height: 40px; cursor: pointer;">
                    <span id="accentHex" style="font-family: 'Space Mono', monospace; font-size: 0.9rem; color: #fff;">#00d4ff</span>
                </div>
            </div>

            <div style="margin-bottom: 2rem;">
                <div class="card-title" style="margin-bottom: 1rem;">Circuit Grid Intensity</div>
                <input type="range" min="0" max="100" value="15" class="slider" id="gridSlider" oninput="updateGrid(this.value)" style="width: 100%; accent-color: var(--accent-primary);">
            </div>
            
            <div style="margin-bottom: 2rem;">
                <div class="card-title" style="margin-bottom: 1rem;">Interface Mode</div>
                <div style="display: flex; gap: 0.5rem;">
                    <button class="nav-btn active" id="modeDark" style="flex: 1; font-size: 0.7rem;" onclick="updateMode('dark')">Dark</button>
                    <button class="nav-btn" id="modeLight" style="flex: 1; font-size: 0.7rem;" onclick="updateMode('light')">Light</button>
                </div>
            </div>

            <div style="margin-bottom: 2rem;">
                <div class="card-title" style="margin-bottom: 1rem;">Language</div>
                <div style="display: flex; gap: 0.5rem;">
                    <button class="nav-btn" id="btnLangES" style="flex: 1; font-size: 0.7rem;" onclick="setLang('es')">ES</button>
                    <button class="nav-btn" id="btnLangEN" style="flex: 1; font-size: 0.7rem;" onclick="setLang('en')">EN</button>
                </div>
            </div>

            <button class="nav-btn" style="width: 100%; margin-top: 1rem; border-color: var(--accent-red); color: var(--accent-red);" onclick="resetTheme()">RESET TO DEFAULT</button>
        </div>
        <!-- ANNUAL VIEW -->
        <section id="annualView" class="view-section active">
             <div class="calendar-header">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <h1 id="annualTitle">Annual Performance</h1>
                    <select id="yearSelector" onchange="updateAnnualView()" style="background: var(--card-bg); color: var(--text-primary); border: 1px solid var(--border-color); padding: 0.5rem; border-radius: 0.5rem; font-family: inherit; font-size: 1rem; cursor: pointer;"></select>
                </div>
            </div>
             <div class="grid">
                <div class="card">
                    <div class="card-title">Gross P&L</div>
                    <div class="card-value" id="annual_gross_pl">-</div>
                </div>
                <div class="card">
                    <div class="card-title">Fees</div>
                    <div class="card-value negative" id="annual_fees">-</div>
                </div>
                <div class="card">
                    <div class="card-title">Net P&L</div>
                    <div class="card-value" id="annual_net_pl">-</div>
                </div>
                <div class="card">
                    <div class="card-title">Expenses</div>
                    <div class="card-value negative" id="annual_expenses">-</div>
                </div>
                <div class="card">
                    <div class="card-title">Profit Factor</div>
                    <div class="card-value" id="annual_pf">-</div>
                </div>
                <div class="card">
                    <div class="card-title">Win Rate</div>
                    <div class="card-value" id="annual_wr">-</div>
                </div>
                <div class="card">
                    <div class="card-title">Total Trades</div>
                    <div class="card-value" id="annual_trades">-</div>
                </div>
            </div>
            <div style="display: flex; gap: 1.5rem; margin-bottom: 1.5rem; align-items: stretch;">
                <div class="card" style="flex: 2; margin-bottom: 0;">
                    <div class="card-title">Performance Analysis (YTD)</div>
                    <div style="display: flex; flex-direction: column; gap: 1rem;">
                        <div>
                            <div class="card-title" style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Cumulative Equity</div>
                            <div class="chart-container" style="height: 250px;"><canvas id="equityChartAnnual"></canvas></div>
                        </div>
                        <div>
                            <div class="card-title" style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Drawdown</div>
                            <div class="chart-container" style="height: 150px;"><canvas id="drawdownChartAnnual"></canvas></div>
                        </div>
                    </div>
                </div>
                <div class="card" style="flex: 1; margin-bottom: 0; display: flex; flex-direction: column;">
                     <div class="card-title">Monthly Net P&L</div>
                     <div class="chart-container" style="flex-grow: 1; min-height: 400px;"><canvas id="monthlyChartAnnual"></canvas></div>
                </div>
            </div>
            <h3 style="margin-bottom: 1rem;">Select a Month</h3>
            <div class="annual-grid" id="annualMonthGrid"></div>
        </section>

        <!-- MONTHLY VIEW -->
        <section id="monthlyView" class="view-section">
             <div class="calendar-header" style="margin-bottom: 0.5rem;"> <h1 id="monthlyViewTitle" style="font-size: 1.5rem;">Monthly Analysis</h1> </div>
             <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1rem; background: var(--hover-bg); padding: 0.75rem; border-radius: 0.5rem;" id="monthlyStatsDashboard"></div>
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
                <div class="card" style="flex: 2; margin-bottom: 0;">
                    <div class="calendar-header">
                        <div><span class="card-title">Calendar</span><h2 id="currentMonthDisplay" style="margin: 0;">-</h2></div>
                        <div><button class="calendar-nav-btn" onclick="changeMonth(-1)">Prev</button><button class="calendar-nav-btn" onclick="changeMonth(1)">Next</button></div>
                    </div>
                    <div class="calendar-grid" id="calendarGrid"></div>
                </div>
                <div class="card" style="flex: 1; margin-bottom: 0;">
                     <div class="card-title">Gain / Loss Stats <span id="glStatsMonthLabel"></span></div>
                     <div style="overflow-x: auto;">
                        <table style="text-align: center;">
                            <thead><tr><th style="text-align: left;">Metric</th><th style="text-align: center;">Won</th><th style="text-align: center;">Lost</th></tr></thead>
                            <tbody id="gainLossBody">
                                 <tr> <td style="text-align: left;">Total P&L</td> <td id="gl_total_won" class="positive">-</td> <td id="gl_total_lost" class="negative">-</td> </tr>
                                 <tr> <td style="text-align: left;">Avg P&L ($)</td> <td id="gl_avg_won" class="positive">-</td> <td id="gl_avg_lost" class="negative">-</td> </tr>
                                 <tr> <td style="text-align: left;">Avg P&L (%)</td> <td id="gl_pct_won" class="positive">-</td> <td id="gl_pct_lost" class="negative">-</td> </tr>
                                 <tr> <td style="text-align: left;">Trades</td> <td id="gl_count_won">-</td> <td id="gl_count_lost">-</td> </tr>
                                 
                                 <tr style="border-top: 2px solid var(--border-color);"> <td style="text-align: left;">Streak</td> <td id="gl_streak_win">-</td> <td id="gl_streak_loss">-</td> </tr>
                                 <tr> <td style="text-align: left;">Fixed Expenses</td> <td id="gl_expenses" class="negative" colspan="2">-</td> </tr>
                            </tbody>
                        </table>
                     </div>
                </div>
            </div>
            
            <div class="card" style="margin-bottom: 1rem;">
                <div class="card-title">Monthly Performance Charts</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                     <div>
                        <div class="card-title" style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.5rem; text-align: center;">Cumulative Equity</div>
                        <div class="chart-container" style="height: 160px;"><canvas id="monthlyEquityChart"></canvas></div>
                     </div>
                     <div>
                        <div class="card-title" style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.5rem; text-align: center;">Daily Net P&L</div>
                        <div class="chart-container" style="height: 160px;"><canvas id="monthlyDailyBarChart"></canvas></div>
                     </div>
                </div>
            </div>
            <div class="card">
                 <div class="card-title">Monthly Ticker Performance <span id="tickerMonthLabel"></span></div>
                 <div style="overflow-x: auto; max-height: 400px; overflow-y: auto;">
                    <table id="monthlyTickersTable"><thead><tr><th>Symbol</th><th>Trades</th><th>Net P&L</th></tr></thead><tbody></tbody></table>
                 </div>
            </div>
        </section>

        <!-- DAILY VIEW -->
        <section id="dailyView" class="view-section">
            <div class="calendar-header"><h1>Daily Details</h1><h2 id="dailyDateTitle" style="color: var(--accent_blue);">-</h2><button onclick="saveTagsToFile()" style="background:var(--accent-primary); color:#000; border:none; padding:0.4rem 1rem; border-radius:8px; cursor:pointer; font-weight:600; font-size:0.8rem; margin-left:auto;">&#128190; Save Tags</button></div>
            <div class="grid" id="dailyStatsGrid">
                <div class="card"><div class="card-title">Daily P&L</div><div class="card-value" id="daily_pnl">-</div></div>
                <div class="card"><div class="card-title">Trades</div><div class="card-value" id="daily_trades_count">-</div></div>
                <div class="card"><div class="card-title">Commissions</div><div class="card-value negative" id="daily_commissions">-</div></div>
            </div>
            
            <div class="card" style="margin-bottom: 2rem;">
                 <div class="card-title">Gain / Loss Stats</div>
                 <div style="overflow-x: auto;">
                    <table style="text-align: center;">
                        <thead><tr><th style="text-align: left;">Metric</th><th style="text-align: center;">Won</th><th style="text-align: center;">Lost</th></tr></thead>
                        <tbody id="dailyGainLossBody">
                             <tr> <td style="text-align: left;">Total P&L</td> <td id="d_gl_total_won" class="positive">-</td> <td id="d_gl_total_lost" class="negative">-</td> </tr>
                             <tr> <td style="text-align: left;">Avg P&L ($)</td> <td id="d_gl_avg_won" class="positive">-</td> <td id="d_gl_avg_lost" class="negative">-</td> </tr>
                             <tr> <td style="text-align: left;">Avg P&L (%)</td> <td id="d_gl_pct_won" class="positive">-</td> <td id="d_gl_pct_lost" class="negative">-</td> </tr>
                             <tr> <td style="text-align: left;">Trades</td> <td id="d_gl_count_won">-</td> <td id="d_gl_count_lost">-</td> </tr>
                             
                             <tr style="border-top: 2px solid var(--border-color);"> <td style="text-align: left; font-weight: 700;">Ratios</td> <td id="d_gl_ratio_wl">-</td> <td id="d_gl_ratio_gp">-</td> </tr>
                             <tr> <td style="text-align: left;">Gastos</td> <td id="d_gl_fees" class="negative">-</td> <td>-</td> </tr>
                             <tr> <td style="text-align: left;">Max Drawdown</td> <td>-</td> <td id="d_gl_max_dd" class="negative">-</td> </tr>
                             <tr> <td style="text-align: left;">Max Streak</td> <td id="d_gl_streak_win">-</td> <td id="d_gl_streak_loss">-</td> </tr>
                             <tr style="border-top: 2px solid var(--border-color);"> <td style="text-align: left; font-weight: 700;">Trade Notes</td> <td colspan="2" id="d_gl_notes" style="text-align:left; color:var(--text-secondary); font-size:0.8rem;">-</td> </tr>
                        </tbody>
                    </table>
                 </div>
            </div>

            <div class="card" style="margin-bottom: 2rem;">
                 <div class="card-title">Day Equity & Execution</div>
                 <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; align-items: start;">
                     <div class="chart-container" style="height: 300px;">
                        <canvas id="dailyEquityChart"></canvas>
                     </div>
                     <div style="overflow-x: auto; max-height: 400px; overflow-y: auto;">
                        <table id="dailyTradesTable"><thead><tr><th>Symbol</th><th>Dir</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Entry Tag</th><th>Exit Tag</th></tr></thead><tbody></tbody></table>
                     </div>
                 </div>
            </div>
        </section>

        <!-- RATIOS VIEW -->
        <section id="ratiosView" class="view-section">
            <div class="calendar-header">
                <div><span class="card-title">Detailed Ratios</span><h1 id="ratiosTitle">-</h1></div>
                <div><button class="calendar-nav-btn" onclick="changeMonth(-1)">Prev</button><button class="calendar-nav-btn" onclick="changeMonth(1)">Next</button></div>
            </div>
            <div class="grid" id="ratiosGrid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));"></div>
        </section>

        <!-- BUILD REPORT VIEW -->
        <section id="buildReportView" class="view-section">
            <div class="build-report-layout">
                <!-- Global Actions -->
                <div class="br-actions">
                    <span style="font-family:'Orbitron',sans-serif; font-size:0.8rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.05em; padding-top:0.4rem; white-space:nowrap;">Or build a custom report below</span>
                    <div class="br-actions-center">
                        <button class="br-btn br-btn-secondary" onclick="resetBuildReport()">Reset</button>
                        <button class="br-btn br-btn-primary" onclick="generateBuildReport()">Generate Report</button>
                    </div>
                </div>

                <!-- Dual Filter Panels -->
                <div class="br-filters-container">
                    <!-- Group A -->
                    <div class="br-panel">
                        <div class="br-panel-header">
                            <span>Group A <span class="br-badge br-badge-a">A</span></span>
                            <span class="count" id="br-count-a">Trades matches: <strong>0</strong></span>
                        </div>
                        <div class="br-row">
                            <div>
                                <div class="br-panel-label">Symbol</div>
                                <input type="text" class="br-input" id="br-symbol-a" placeholder="e.g. AAPL,TSLA" oninput="updateBuildCounts()" />
                            </div>
                            <div>
                                <div class="br-panel-label">Tags</div>
                                <div class="br-tag-wrap">
                                    <div class="br-tag-select" id="br-tags-select-a" onclick="toggleTagDropdown('a')">
                                        <span id="br-tags-placeholder-a" style="color:var(--text-secondary); font-size:0.85rem;">Select tags...</span>
                                        <span id="br-tags-chips-a"></span>
                                    </div>
                                    <div class="br-tag-dropdown" id="br-tags-dropdown-a"></div>
                                </div>
                            </div>
                        </div>
                        <div class="br-row">
                            <div>
                                <div class="br-panel-label">Side</div>
                                <select class="br-select" id="br-side-a" onchange="updateBuildCounts()">
                                    <option value="all">All</option>
                                    <option value="Long">Long</option>
                                    <option value="Short">Short</option>
                                </select>
                            </div>
                            <div>
                                <div class="br-panel-label">Duration</div>
                                <select class="br-select" id="br-duration-a" onchange="updateBuildCounts()">
                                    <option value="all">All</option>
                                    <option value="day">Day</option>
                                    <option value="swing">Swing</option>
                                </select>
                            </div>
                        </div>
                        <div class="br-row">
                            <div>
                                <div class="br-panel-label">Trade P&amp;L</div>
                                <select class="br-select" id="br-pnl-a" onchange="updateBuildCounts()">
                                    <option value="all">All</option>
                                    <option value="winning">Winning</option>
                                    <option value="losing">Losing</option>
                                    <option value="breakeven">Break Even</option>
                                </select>
                            </div>
                            <div>
                                <div class="br-panel-label">Date Range</div>
                                <div style="display:flex; gap:0.4rem; align-items:center;">
                                    <input type="date" class="br-input" id="br-datefrom-a" style="flex:1; min-width:0;" onchange="updateBuildCounts()" />
                                    <span style="color:var(--text-secondary); font-size:0.75rem;">—</span>
                                    <input type="date" class="br-input" id="br-dateto-a" style="flex:1; min-width:0;" onchange="updateBuildCounts()" />
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Group B -->
                    <div class="br-panel">
                        <div class="br-panel-header">
                            <span>Group B <span class="br-badge br-badge-b">B</span></span>
                            <span class="count" id="br-count-b">Trades matches: <strong>0</strong></span>
                        </div>
                        <div class="br-row">
                            <div>
                                <div class="br-panel-label">Symbol</div>
                                <input type="text" class="br-input" id="br-symbol-b" placeholder="e.g. AAPL,TSLA" oninput="updateBuildCounts()" />
                            </div>
                            <div>
                                <div class="br-panel-label">Tags</div>
                                <div class="br-tag-wrap">
                                    <div class="br-tag-select" id="br-tags-select-b" onclick="toggleTagDropdown('b')">
                                        <span id="br-tags-placeholder-b" style="color:var(--text-secondary); font-size:0.85rem;">Select tags...</span>
                                        <span id="br-tags-chips-b"></span>
                                    </div>
                                    <div class="br-tag-dropdown" id="br-tags-dropdown-b"></div>
                                </div>
                            </div>
                        </div>
                        <div class="br-row">
                            <div>
                                <div class="br-panel-label">Side</div>
                                <select class="br-select" id="br-side-b" onchange="updateBuildCounts()">
                                    <option value="all">All</option>
                                    <option value="Long">Long</option>
                                    <option value="Short">Short</option>
                                </select>
                            </div>
                            <div>
                                <div class="br-panel-label">Duration</div>
                                <select class="br-select" id="br-duration-b" onchange="updateBuildCounts()">
                                    <option value="all">All</option>
                                    <option value="day">Day</option>
                                    <option value="swing">Swing</option>
                                </select>
                            </div>
                        </div>
                        <div class="br-row">
                            <div>
                                <div class="br-panel-label">Trade P&amp;L</div>
                                <select class="br-select" id="br-pnl-b" onchange="updateBuildCounts()">
                                    <option value="all">All</option>
                                    <option value="winning">Winning</option>
                                    <option value="losing">Losing</option>
                                    <option value="breakeven">Break Even</option>
                                </select>
                            </div>
                            <div>
                                <div class="br-panel-label">Date Range</div>
                                <div style="display:flex; gap:0.4rem; align-items:center;">
                                    <input type="date" class="br-input" id="br-datefrom-b" style="flex:1; min-width:0;" onchange="updateBuildCounts()" />
                                    <span style="color:var(--text-secondary); font-size:0.75rem;">—</span>
                                    <input type="date" class="br-input" id="br-dateto-b" style="flex:1; min-width:0;" onchange="updateBuildCounts()" />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Results Comparison Table -->
                <div id="br-results" class="br-panel" style="display:none;">
                    <div class="br-panel-header">
                        <span>Comparison Results</span>
                    </div>
                    <div id="br-table-container"></div>
                </div>
            </div>
        </section>
    </main>

    <!-- TAG EDITOR MODAL -->
    <div id="tagModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); z-index:9999; align-items:center; justify-content:center;">
        <div style="background:var(--card-bg); border:1px solid var(--border-color); border-radius:16px; padding:2rem; max-width:520px; width:90%; box-shadow:0 0 40px rgba(0,212,255,0.15);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
                <h2 style="margin:0; color:var(--accent-primary);" id="modalTitle">-</h2>
                <button onclick="closeTagModal()" style="background:none; border:none; color:var(--text-secondary); font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <div style="margin-bottom:1rem;">
                <div style="color:var(--text-secondary); margin-bottom:0.5rem; font-size:0.85rem;">Trade Details</div>
                <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.5rem; margin-bottom:1rem;">
                    <div><span style="color:var(--text-secondary);">Symbol:</span> <strong style="color:#60a5fa;" id="modalSymbol">-</strong></div>
                    <div><span style="color:var(--text-secondary);">Dir:</span> <strong id="modalDir">-</strong></div>
                    <div><span style="color:var(--text-secondary);">Qty:</span> <strong id="modalQty">-</strong></div>
                    <div><span style="color:var(--text-secondary);">Entry:</span> <strong id="modalEntry">-</strong></div>
                    <div><span style="color:var(--text-secondary);">Exit:</span> <strong id="modalExit">-</strong></div>
                    <div><span style="color:var(--text-secondary);">P&L:</span> <strong id="modalPnL">-</strong></div>
                </div>
            </div>
            <div style="margin-bottom:1rem;">
                <label style="color:var(--text-secondary); font-size:0.85rem;">Entry Tag</label>
                <div id="entryTagPresets" style="display:flex; flex-wrap:wrap; gap:0.4rem; margin:0.5rem 0;"></div>
                <input id="entryTagInput" placeholder="Or type custom..." style="width:100%; background:rgba(255,255,255,0.05); border:1px solid var(--border-color); color:var(--text-primary); padding:0.5rem; border-radius:8px; box-sizing:border-box;">
            </div>
            <div style="margin-bottom:1rem;">
                <label style="color:var(--text-secondary); font-size:0.85rem;">Exit Tag</label>
                <div id="exitTagPresets" style="display:flex; flex-wrap:wrap; gap:0.4rem; margin:0.5rem 0;"></div>
                <input id="exitTagInput" placeholder="Or type custom..." style="width:100%; background:rgba(255,255,255,0.05); border:1px solid var(--border-color); color:var(--text-primary); padding:0.5rem; border-radius:8px; box-sizing:border-box;">
            </div>
            <div style="margin-bottom:1.5rem;">
                <label style="color:var(--text-secondary); font-size:0.85rem;">Note</label>
                <textarea id="noteInput" placeholder="Optional note..." rows="2" style="width:100%; background:rgba(255,255,255,0.05); border:1px solid var(--border-color); color:var(--text-primary); padding:0.5rem; border-radius:8px; box-sizing:border-box; resize:vertical;"></textarea>
            </div>
            <div style="display:flex; gap:1rem; justify-content:flex-end;">
                <button onclick="saveTagEntry()" style="background:var(--accent-primary); color:#000; border:none; padding:0.6rem 1.5rem; border-radius:8px; cursor:pointer; font-weight:600;">Save & Close</button>
                <button onclick="closeTagModal()" style="background:rgba(255,255,255,0.1); color:var(--text-primary); border:none; padding:0.6rem 1.5rem; border-radius:8px; cursor:pointer;">Cancel</button>
            </div>
        </div>
    </div>

    <script>
        const annualStats = {annual_stats_json};
            const annualCharts = {annual_charts_json};
            const availableYears = {available_years_json};
            
            const dailyData = {daily_data_json};
            const monthlyData = {monthly_data_json};
            const monthlySymbols = {monthly_symbols_json};
            const monthlyStats = {monthly_stats_json};
            const monthlyGainLoss = {monthly_gain_loss_json};
            const monthlyEquityData = {monthly_equity_json};
            const dailyEquityData = {daily_equity_json};
            const dailyTags = {daily_tags_json};

            // --- i18n ---
            const savedLang = localStorage.getItem('lang');
            let LANG = savedLang || (navigator.language.startsWith('es') ? 'es' : 'en');

            const TK = {{
                en: {{
                    performance: "Performance",
                    annualBoard: "Annual Board",
                    calendar: "Calendar",
                    dailyDetails: "Daily Details",
                    ratios: "Ratios",
                    customize: "CUSTOMIZE",
                    themeConfig: "THEME CONFIG",
                    quickPresets: "Quick Presets",
                    tronCyan: "Tron Cyan",
                    matrix: "Matrix",
                    redAlert: "Red Alert",
                    purpleRain: "Purple Rain",
                    goldEmber: "Gold Ember",
                    monoSteel: "Mono Steel",
                    primaryAccent: "Primary Accent",
                    circuitGridIntensity: "Circuit Grid Intensity",
                    interfaceMode: "Interface Mode",
                    dark: "Dark",
                    light: "Light",
                    resetToDefault: "RESET TO DEFAULT",
                    language: "Language",
                    annualPerformance: "Annual Performance",
                    grossPL: "Gross P&L",
                    fees: "Fees",
                    netPL: "Net P&L",
                    expenses: "Expenses",
                    profitFactor: "Profit Factor",
                    winRate: "Win Rate",
                    totalTrades: "Total Trades",
                    performanceAnalysis: "Performance Analysis (YTD)",
                    cumulativeEquity: "Cumulative Equity",
                    drawdown: "Drawdown",
                    monthlyNetPL: "Monthly Net P&L",
                    selectMonth: "Select a Month",
                    monthlyAnalysis: "Monthly Analysis",
                    prev: "Prev",
                    next: "Next",
                    gainLossStats: "Gain / Loss Stats",
                    metric: "Metric",
                    won: "Won",
                    lost: "Lost",
                    totalPL: "Total P&L",
                    avgPL: "Avg P&L ($)",
                    avgPLPct: "Avg P&L (%)",
                    trades: "Trades",
                    streak: "Streak",
                    maxStreak: "Max Streak",
                    maxDrawdown: "Max Drawdown",
                    avgWinLoss: "Avg Win / Loss",
                    ratiosRow: "Ratios",
                    expensesRow: "Expenses",
                    tradeNotes: "Trade Notes",
                    fixedExpenses: "Fixed Expenses",
                    monthlyPerformanceCharts: "Monthly Performance Charts",
                    dailyNetPL: "Daily Net P&L",
                    monthlyTickerPerformance: "Monthly Ticker Performance",
                    symbol: "Symbol",
                    netPLCol: "Net P&L",
                    tradesCol: "Trades",
                    saveTags: "Save Tags",
                    dailyPL: "Daily P&L",
                    commissions: "Commissions",
                    dayEquityExecution: "Day Equity & Execution",
                    dir: "Dir",
                    qty: "Qty",
                    entry: "Entry",
                    exit: "Exit",
                    pl: "P&L",
                    entryTag: "Entry Tag",
                    exitTag: "Exit Tag",
                    detailedRatios: "Detailed Ratios",
                    netProfit: "Net Profit",
                    winRateW1: "Win Rate (W:1)",
                    winningTrades: "Winning Trades",
                    losingTrades: "Losing Trades",
                    longVsShort: "Long vs Short",
                    gainPainRatio: "Gain / Pain Ratio",
                    expectancy: "Expectancy",
                    maxConsecWins: "Max Consec Wins",
                    maxConsecLosses: "Max Consec Losses",
                    advancedPerformanceRatios: "Advanced Performance Ratios",
                    edgeScore: "Edge Score",
                    recoveryFactor: "Recovery Factor",
                    payoffRatio: "Payoff Ratio",
                    calmarRatio: "Calmar Ratio",
                    sharpeRatio: "Sharpe Ratio",
                    sortinoRatio: "Sortino Ratio",
                    sqn: "SQN",
                    consistencyRatio: "Consistency Ratio",
                    zScore: "Z-Score",
                    profitFactorL: "Profit Factor (L)",
                    profitFactorS: "Profit Factor (S)",
                    winRateL: "Win Rate (L)",
                    winRateS: "Win Rate (S)",
                    tradesPerDay: "Trades per Day",
                    maxDDDuration: "Max DD Duration",
                    equityPeak: "Equity Peak",
                    stdDevPL: "Std Dev P&L",
                    standardError: "Standard Error",
                    tScore: "T-Score",
                    avgTimeWin: "Avg Time Win",
                    kellyCriterion: "Kelly Criterion",
                    tradedDays: "Traded Days",
                    tradingCommissions: "Trading Commissions",
                    avgDailyPL: "Avg Daily P&L",
                    tagPerformance: "Tag Performance",
                    tag: "Tag",
                    count: "Count",
                    weekdayPerformance: "Weekday Performance",
                    day: "Day",
                    totalPLDay: "Total P&L",
                    noData: "No Data",
                    noDataDash: "No data",
                    selectDayCalendar: "Select a day from the calendar",
                    tradeDetails: "Trade Details",
                    entryTagLabel: "Entry Tag",
                    exitTagLabel: "Exit Tag",
                    orTypeCustom: "Or type custom...",
                    note: "Note",
                    optionalNote: "Optional note...",
                    saveClose: "Save & Close",
                    cancel: "Cancel",
                    tagsSaved: "Tags saved!",
                    tagsDownloaded: "tags.json downloaded -- place it in Reportes_Brokers/",
                    untagged: "Untagged",
                    week: "Week",
                    trds: "trds",
                    wlRatio: "W/L",
                    gpRatio: "G/P",
                    symbolLabel: "Symbol:",
                    dirLabel: "Dir:",
                    qtyLabel: "Qty:",
                    entryLabel: "Entry:",
                    exitLabel: "Exit:",
                    plLabel: "P&L:",
                    errorLoadingDashboard: "Error loading dashboard:",
                    dailyPLChart: "Daily P&L",
                    monthEquity: "Month Equity",
                    monthEquityChart: "Month Equity",
                    longPct: "Long (...%)",
                    shortPct: "Short (...%)",
                }},
                es: {{
                    performance: "Rendimiento",
                    annualBoard: "Tablero Anual",
                    calendar: "Calendario",
                    dailyDetails: "Detalle Diario",
                    ratios: "Metricas",
                    customize: "PERSONALIZAR",
                    themeConfig: "CONFIG TEMA",
                    quickPresets: "Presets Rapidos",
                    tronCyan: "Tron Cyan",
                    matrix: "Matrix",
                    redAlert: "Alerta Roja",
                    purpleRain: "Lluvia Purpura",
                    goldEmber: "Ambar Dorado",
                    monoSteel: "Acero Mono",
                    primaryAccent: "Color Principal",
                    circuitGridIntensity: "Intensidad de la Cuadricula",
                    interfaceMode: "Modo de Interfaz",
                    dark: "Oscuro",
                    light: "Claro",
                    resetToDefault: "RESTAURAR VALORES",
                    language: "Idioma",
                    annualPerformance: "Rendimiento Anual",
                    grossPL: "Ganancia Bruta",
                    fees: "Comisiones",
                    netPL: "Ganancia Neta",
                    expenses: "Gastos",
                    profitFactor: "Factor de Ganancia",
                    winRate: "Tasa de Acierto",
                    totalTrades: "Total Trades",
                    performanceAnalysis: "Analisis de Rendimiento (YTD)",
                    cumulativeEquity: "Equidad Acumulada",
                    drawdown: "Drawdown",
                    monthlyNetPL: "P&L Neto Mensual",
                    selectMonth: "Selecciona un Mes",
                    monthlyAnalysis: "Analisis Mensual",
                    prev: "Anterior",
                    next: "Siguiente",
                    gainLossStats: "Estadisticas G/P",
                    metric: "Metrica",
                    won: "Ganados",
                    lost: "Perdidos",
                    totalPL: "P&L Total",
                    avgPL: "Prom P&L ($)",
                    avgPLPct: "Prom P&L (%)",
                    trades: "Trades",
                    streak: "Racha",
                    maxStreak: "Racha Max",
                    maxDrawdown: "Drawdown Max",
                    avgWinLoss: "Prom Gan/Perd",
                    ratiosRow: "Ratios",
                    expensesRow: "Gastos",
                    tradeNotes: "Notas de Trades",
                    fixedExpenses: "Gastos Fijos",
                    monthlyPerformanceCharts: "Graficas de Rendimiento Mensual",
                    dailyNetPL: "P&L Neto Diario",
                    monthlyTickerPerformance: "Rendimiento Mensual por Ticker",
                    symbol: "Simbolo",
                    netPLCol: "P&L Neto",
                    tradesCol: "Trades",
                    saveTags: "Guardar Tags",
                    dailyPL: "P&L Diario",
                    commissions: "Comisiones",
                    dayEquityExecution: "Equidad y Ejecucion del Dia",
                    dir: "Dir",
                    qty: "Cant",
                    entry: "Entrada",
                    exit: "Salida",
                    pl: "P&L",
                    entryTag: "Tag Entrada",
                    exitTag: "Tag Salida",
                    detailedRatios: "Ratios Detallados",
                    netProfit: "Ganancia Neta",
                    winRateW1: "Tasa Acierto (W:1)",
                    winningTrades: "Trades Ganadores",
                    losingTrades: "Trades Perdedores",
                    longVsShort: "Long vs Short",
                    gainPainRatio: "Ratio G/P",
                    expectancy: "Expectativa",
                    maxConsecWins: "Max Ganados Consec",
                    maxConsecLosses: "Max Perdidos Consec",
                    advancedPerformanceRatios: "Ratios de Rendimiento Avanzados",
                    edgeScore: "Edge Score",
                    recoveryFactor: "Factor de Recuperacion",
                    payoffRatio: "Payoff Ratio",
                    calmarRatio: "Calmar Ratio",
                    sharpeRatio: "Sharpe Ratio",
                    sortinoRatio: "Sortino Ratio",
                    sqn: "SQN",
                    consistencyRatio: "Ratio de Consistencia",
                    zScore: "Z-Score",
                    profitFactorL: "Factor Ganancia (L)",
                    profitFactorS: "Factor Ganancia (S)",
                    winRateL: "Tasa Acierto (L)",
                    winRateS: "Tasa Acierto (S)",
                    tradesPerDay: "Trades por Dia",
                    maxDDDuration: "Duracion Max DD",
                    equityPeak: "Pico de Equidad",
                    stdDevPL: "Desviacion Estandar P&L",
                    standardError: "Error Estandar",
                    tScore: "T-Score",
                    avgTimeWin: "Tiempo Prom Ganador",
                    kellyCriterion: "Criterio de Kelly",
                    tradedDays: "Dias Tradeados",
                    tradingCommissions: "Comisiones de Trading",
                    avgDailyPL: "Prom P&L Diario",
                    tagPerformance: "Rendimiento por Tag",
                    tag: "Tag",
                    count: "Cuenta",
                    weekdayPerformance: "Rendimiento por Dia",
                    day: "Dia",
                    totalPLDay: "P&L Total",
                    noData: "Sin Datos",
                    noDataDash: "Sin datos",
                    selectDayCalendar: "Selecciona un dia del calendario",
                    tradeDetails: "Detalles del Trade",
                    entryTagLabel: "Tag de Entrada",
                    exitTagLabel: "Tag de Salida",
                    orTypeCustom: "O escribe uno...",
                    note: "Nota",
                    optionalNote: "Nota opcional...",
                    saveClose: "Guardar y Cerrar",
                    cancel: "Cancelar",
                    tagsSaved: "Tags guardados!",
                    tagsDownloaded: "tags.json descargado -- colocalo en Reportes_Brokers/",
                    untagged: "Sin Tag",
                    week: "Sem",
                    trds: "trades",
                    wlRatio: "W/L",
                    gpRatio: "G/P",
                    symbolLabel: "Simbolo:",
                    dirLabel: "Dir:",
                    qtyLabel: "Cant:",
                    entryLabel: "Entrada:",
                    exitLabel: "Salida:",
                    plLabel: "P&L:",
                    errorLoadingDashboard: "Error cargando dashboard:",
                    dailyPLChart: "P&L Diario",
                    monthEquity: "Equidad del Mes",
                    monthEquityChart: "Equidad del Mes",
                    longPct: "Long (...%)",
                    shortPct: "Short (...%)",
                }}
            }};

            function t(key) {{
                return (TK[LANG] && TK[LANG][key]) || (TK['en'] && TK['en'][key]) || key;
            }}

            function refreshStaticText() {{
                // Walk all elements with data-i18n attribute
                document.querySelectorAll('[data-i18n]').forEach(el => {{
                    const key = el.getAttribute('data-i18n');
                    if (el.tagName === 'INPUT' && (el.type === 'text' || el.tagName === 'TEXTAREA')) {{
                        el.placeholder = t(key);
                    }} else if (el.tagName === 'INPUT') {{
                        // skip
                    }} else {{
                        el.innerText = t(key);
                    }}
                }});
                // Update all card-title elements by matching known English/Spanish text
                const i18nMap = {{
                    'Gross P&L': 'grossPL', 'Ganancia Bruta': 'grossPL',
                    'Fees': 'fees', 'Comisiones': 'fees',
                    'Net P&L': 'netPL', 'Ganancia Neta': 'netPL',
                    'Expenses': 'expenses', 'Gastos': 'expenses',
                    'Profit Factor': 'profitFactor', 'Factor de Ganancia': 'profitFactor',
                    'Win Rate': 'winRate', 'Tasa de Acierto': 'winRate',
                    'Total Trades': 'totalTrades',
                    'Performance Analysis (YTD)': 'performanceAnalysis', 'Analisis de Rendimiento (YTD)': 'performanceAnalysis',
                    'Cumulative Equity': 'cumulativeEquity', 'Equidad Acumulada': 'cumulativeEquity',
                    'Drawdown': 'drawdown',
                    'Monthly Net P&L': 'monthlyNetPL', 'P&L Neto Mensual': 'monthlyNetPL',
                    'Select a Month': 'selectMonth', 'Selecciona un Mes': 'selectMonth',
                    'Monthly Analysis': 'monthlyAnalysis', 'Analisis Mensual': 'monthlyAnalysis',
                    'Calendar': 'calendar', 'Calendario': 'calendar',
                    'Prev': 'prev', 'Anterior': 'prev',
                    'Next': 'next', 'Siguiente': 'next',
                    'Gain / Loss Stats': 'gainLossStats', 'Estadisticas G/P': 'gainLossStats',
                    'Metric': 'metric', 'Metrica': 'metric',
                    'Won': 'won', 'Ganados': 'won',
                    'Lost': 'lost', 'Perdidos': 'lost',
                    'Streak': 'streak', 'Racha': 'streak',
                    'Max Streak': 'maxStreak', 'Racha Max': 'maxStreak',
                    'Max Drawdown': 'maxDrawdown', 'Drawdown Max': 'maxDrawdown',
                    'Fixed Expenses': 'fixedExpenses', 'Gastos Fijos': 'fixedExpenses',
                    'Monthly Performance Charts': 'monthlyPerformanceCharts', 'Graficas de Rendimiento Mensual': 'monthlyPerformanceCharts',
                    'Daily Net P&L': 'dailyNetPL', 'P&L Neto Diario': 'dailyNetPL',
                    'Monthly Ticker Performance': 'monthlyTickerPerformance', 'Rendimiento Mensual por Ticker': 'monthlyTickerPerformance',
                    'Daily P&L': 'dailyPL', 'P&L Diario': 'dailyPL',
                    'Commissions': 'commissions', 'Comisiones': 'commissions',
                    'Day Equity & Execution': 'dayEquityExecution', 'Equidad y Ejecucion del Dia': 'dayEquityExecution',
                    'Detailed Ratios': 'detailedRatios', 'Ratios Detallados': 'detailedRatios',
                    'Trade Details': 'tradeDetails', 'Detalles del Trade': 'tradeDetails',
                    'Entry Tag': 'entryTag', 'Tag Entrada': 'entryTag',
                    'Exit Tag': 'exitTag', 'Tag Salida': 'exitTag',
                    'Note': 'note', 'Nota': 'note',
                    'Save & Close': 'saveClose', 'Guardar y Cerrar': 'saveClose',
                    'Cancel': 'cancel', 'Cancelar': 'cancel',
                    'RESET TO DEFAULT': 'resetToDefault', 'RESTAURAR VALORES': 'resetToDefault',
                    'THEME CONFIG': 'themeConfig', 'CONFIG TEMA': 'themeConfig',
                    'Tron Cyan': 'tronCyan',
                    'Matrix': 'matrix',
                    'Red Alert': 'redAlert', 'Alerta Roja': 'redAlert',
                    'Purple Rain': 'purpleRain', 'Lluvia Purpura': 'purpleRain',
                    'Gold Ember': 'goldEmber', 'Ambar Dorado': 'goldEmber',
                    'Mono Steel': 'monoSteel', 'Acero Mono': 'monoSteel',
                    'Dark': 'dark', 'Oscuro': 'dark',
                    'Light': 'light', 'Claro': 'light',
                    'Quick Presets': 'quickPresets', 'Presets Rapidos': 'quickPresets',
                    'Primary Accent': 'primaryAccent', 'Color Principal': 'primaryAccent',
                    'Circuit Grid Intensity': 'circuitGridIntensity', 'Intensidad de la Cuadricula': 'circuitGridIntensity',
                    'Interface Mode': 'interfaceMode', 'Modo de Interfaz': 'interfaceMode',
                    'Language': 'language', 'Idioma': 'language',
                    'Symbol:': 'symbolLabel', 'Simbolo:': 'symbolLabel',
                    'Dir:': 'dirLabel',
                    'Qty:': 'qtyLabel', 'Cant:': 'qtyLabel',
                    'Entry:': 'entryLabel', 'Entrada:': 'entryLabel',
                    'Exit:': 'exitLabel', 'Salida:': 'exitLabel',
                    'P&L:': 'plLabel',
                    'Ratios': 'ratiosRow',
                    'Trade Notes': 'tradeNotes', 'Notas de Trades': 'tradeNotes',
                    'Total P&L': 'totalPL', 'P&L Total': 'totalPL',
                    'Avg P&L ($)': 'avgPL', 'Prom P&L ($)': 'avgPL',
                    'Avg P&L (%)': 'avgPLPct', 'Prom P&L (%)': 'avgPLPct',
                    'Trades': 'trades',
                    'Symbol': 'symbol', 'Simbolo': 'symbol',
                    'Net P&L': 'netPLCol', 'P&L Neto': 'netPLCol',
                    'Dir': 'dir',
                    'Qty': 'qty', 'Cant': 'qty',
                    'Entry': 'entry', 'Entrada': 'entry',
                    'Exit': 'exit', 'Salida': 'exit',
                    'P&L': 'pl',
                    'Annual Performance': 'annualPerformance', 'Rendimiento Anual': 'annualPerformance',
                    'Daily Details': 'dailyDetails', 'Detalle Diario': 'dailyDetails',
                    'Save Tags': 'saveTags', 'Guardar Tags': 'saveTags',
                }};
                document.querySelectorAll('.card-title, th, td, button, label, h1, h2, h3, span, strong').forEach(el => {{
                    if (el.children.length > 0) return; // skip elements with children
                    const txt = el.innerText.trim();
                    if (i18nMap[txt]) {{
                        el.innerText = t(i18nMap[txt]);
                    }}
                }});
                // Update placeholders
                const phMap = {{
                    'Or type custom...': 'orTypeCustom', 'O escribe uno...': 'orTypeCustom',
                    'Optional note...': 'optionalNote', 'Nota opcional...': 'optionalNote',
                }};
                document.querySelectorAll('input[placeholder], textarea[placeholder]').forEach(el => {{
                    if (phMap[el.placeholder]) el.placeholder = t(phMap[el.placeholder]);
                }});
                // Update customization trigger
                document.getElementById('customizationTrigger').innerHTML = '<span style="font-size: 1rem;">🎨</span> ' + t('customize');
                // Update save tags button
                const saveBtn = document.querySelector('#dailyView button[onclick="saveTagsToFile()"]');
                if (saveBtn) saveBtn.innerHTML = '&#128190; ' + t('saveTags');
                // Update Performance subtitle
                const perfEl = document.querySelector('.sidebar p');
                if (perfEl) perfEl.innerText = t('performance');
            }}

            function setLang(lang) {{
                LANG = lang;
                localStorage.setItem('lang', lang);
                document.getElementById('btnLangES').classList.toggle('active', lang === 'es');
                document.getElementById('btnLangEN').classList.toggle('active', lang === 'en');
                document.documentElement.lang = lang;
                document.getElementById('btn-annual').innerText = t('annualBoard');
                document.getElementById('btn-monthly').innerText = t('calendar');
                document.getElementById('btn-daily').innerText = t('dailyDetails');
                document.getElementById('btn-ratios').innerText = t('ratios');
                refreshStaticText();
                // Re-render current view
                if (currentView === 'annual') renderAnnual();
                if (currentView === 'monthly') {{ renderCalendar(); }}
                if (currentView === 'daily') renderDaily();
                if (currentView === 'ratios') renderRatios();
            }}

            // Apply saved lang on load
            (function() {{
                if (savedLang) {{
                    document.documentElement.lang = savedLang;
                    document.getElementById('btnLangES').classList.toggle('active', savedLang === 'es');
                    document.getElementById('btnLangEN').classList.toggle('active', savedLang === 'en');
                }} else {{
                    document.getElementById('btnLang' + (LANG === 'es' ? 'ES' : 'EN')).classList.add('active');
                }}
                document.getElementById('btn-annual').innerText = t('annualBoard');
                document.getElementById('btn-monthly').innerText = t('calendar');
                document.getElementById('btn-daily').innerText = t('dailyDetails');
                document.getElementById('btn-ratios').innerText = t('ratios');
                document.getElementById('customizationTrigger').innerHTML = '<span style="font-size: 1rem;">🎨</span> ' + t('customize');
            }})();

            let currentView = 'annual';
            let currentDate = new Date(); 
            let currentYearView = 'All';
            
            let selectedDayKey = null;
            let monthlyChartInstance = null;
            let monthlyBarChartInstance = null;
            let dailyChartInstance = null;
            let annualEquityChart = null;
            let annualMonthlyChart = null;
            let longShortChartInstance = null;

            function switchView(viewName) {{
                document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
                document.getElementById(viewName + 'View').classList.add('active');
                document.getElementById('btn-' + viewName).classList.add('active');
                currentView = viewName;
                if (viewName === 'annual') renderAnnual();
                if (viewName === 'monthly') renderCalendar();
                if (viewName === 'daily') renderDaily();
                if (viewName === 'ratios') renderRatios();
                if (viewName === 'buildReport') renderBuildReport();
            }}
            
            function renderAnnual() {{
                const sel = document.getElementById('yearSelector');
                if (sel.options.length === 0) {{
                    availableYears.forEach(y => {{
                        const opt = document.createElement('option');
                        opt.value = y;
                        opt.innerText = y;
                        sel.appendChild(opt);
                    }});
                    sel.value = currentYearView;
                }}
                
                const stats = annualStats[currentYearView];
                if(stats) {{
                    const grossEl = document.getElementById('annual_gross_pl');
                    grossEl.innerText = '$' + stats.gross_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                    grossEl.className = 'card-value ' + (stats.gross_pl >= 0 ? 'positive' : 'negative');

                    const feesEl = document.getElementById('annual_fees');
                    feesEl.innerText = '-$' + Math.abs(stats.fees).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});

                    const plEl = document.getElementById('annual_net_pl');
                    plEl.innerText = '$' + stats.net_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                    plEl.className = 'card-value ' + (stats.net_pl >= 0 ? 'positive' : 'negative');

                    const expEl = document.getElementById('annual_expenses');
                    const expenses = stats.expenses || 0;
                    expEl.innerText = '-$' + Math.abs(expenses).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});

                    document.getElementById('annual_pf').innerText = stats.profit_factor === Infinity ? 'Inf' : stats.profit_factor.toFixed(2);
                    document.getElementById('annual_wr').innerText = stats.win_rate.toFixed(2) + '%';
                    document.getElementById('annual_trades').innerText = stats.total_trades;
                }}
                
                if (typeof Chart !== 'undefined') updateAnnualCharts();
                
                const container = document.getElementById('annualMonthGrid');
                container.innerHTML = '';
                const allMonths = Object.keys(monthlyData).sort();
                const visibleMonths = (currentYearView === 'All') ? allMonths : allMonths.filter(m => m.startsWith(currentYearView));
                
                visibleMonths.forEach(mKey => {{
                    const pl = monthlyData[mKey];
                    const stats = monthlyStats[mKey];
                    const card = document.createElement('div');
                    card.className = 'month-card';
                    card.onclick = () => {{ currentDate = new Date(mKey + '-02'); switchView('monthly'); }};
                    card.innerHTML = `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; position:relative; z-index:10;"><span style="font-weight:600; font-size:1.1rem;">${{mKey}}</span><span class="${{pl >= 0 ? 'positive' : 'negative'}}" style="font-weight:700;">${{pl >= 0 ? '+' : '-'}}$${{Math.abs(pl).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span></div><div style="font-size:0.85rem; color:var(--text-secondary); position:relative; z-index:10;"><div>${{t('winRate')}}: ${{stats.win_rate.toFixed(2)}}%</div><div>${{t('trades')}}: ${{stats.total_trades}}</div></div>`;
                    container.appendChild(card);
                }});
            }}
            
            function updateAnnualView() {{
                currentYearView = document.getElementById('yearSelector').value;
                renderAnnual();
            }}

            function updateAnnualCharts() {{
                const data = annualCharts[currentYearView];
                if(!data) return;
                
                const ctxEquity = document.getElementById('equityChartAnnual').getContext('2d');
                if(annualEquityChart) annualEquityChart.destroy();
                annualEquityChart = new Chart(ctxEquity, {{ 
                    type: 'line', 
                    data: {{ 
                        labels: data.equity.labels, 
                        datasets: [{{ 
                            label: 'Cumulative P&L', 
                            data: data.equity.data, 
                            borderColor: '#10b981', 
                            backgroundColor: 'rgba(16, 185, 129, 0.1)', 
                            borderWidth: 2, 
                            pointRadius: 0, 
                            fill: {{
                                target: 'origin',
                                above: 'rgba(16, 185, 129, 0.15)',
                                below: 'rgba(239, 68, 68, 0.15)'
                            }}, 
                            tension: 0.1 
                        }}] 
                    }}, 
                    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ color: '#94a3b8', maxTicksLimit: 20 }}, grid: {{ display: false }} }}, y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }} }} 
                }});

                const ctxDD = document.getElementById('drawdownChartAnnual').getContext('2d');
                if(window.annualDDChart) window.annualDDChart.destroy();
                window.annualDDChart = new Chart(ctxDD, {{
                    type: 'line',
                    data: {{
                        labels: data.drawdown.labels,
                        datasets: [{{
                            label: 'Drawdown',
                            data: data.drawdown.data,
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.15)',
                            borderWidth: 2,
                            pointRadius: 0,
                            fill: true,
                            tension: 0.1
                        }}]
                    }},
                    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }} }}
                }});

                const ctxMonthly = document.getElementById('monthlyChartAnnual').getContext('2d');
                if(annualMonthlyChart) annualMonthlyChart.destroy();
                const barColors = data.monthly.data.map(v => v >= 0 ? '#10b981' : '#ef4444');
                annualMonthlyChart = new Chart(ctxMonthly, {{ 
                    type: 'bar', 
                    data: {{ 
                        labels: data.monthly.labels, 
                        datasets: [{{ 
                            label: 'Monthly P&L', 
                            data: data.monthly.data, 
                            backgroundColor: barColors, 
                            borderRadius: 4 
                        }}] 
                    }}, 
                    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}, x: {{ ticks: {{ color: '#94a3b8' }} }} }} }} 
                }});
            }}

            const monthsEN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
            const monthsES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
            function getMonthName(idx) {{ return LANG === 'es' ? monthsES[idx] : monthsEN[idx]; }}
            const daysEN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Week'];
            const daysES = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sem'];
            function getDayHeaders() {{ return LANG === 'es' ? daysES : daysEN; }}
            function renderCalendar() {{
                const year = currentDate.getFullYear();
                const month = currentDate.getMonth();
                const monthKey = `${{year}}-${{String(month + 1).padStart(2, '0')}}`;
                const monthPnl = monthlyData[monthKey] || 0;
                document.getElementById('currentMonthDisplay').innerHTML = `${{getMonthName(month)}} ${{year}} ${{monthPnl > 0 ? `<span class="positive">(+$${{monthPnl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}})</span>` : (monthPnl < 0 ? `<span class="negative">(-$${{Math.abs(monthPnl).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}})</span>` : `<span>($0.00)</span>`)}}`;

                const grid = document.getElementById('calendarGrid'); grid.innerHTML = '';
                getDayHeaders().forEach(d => {{ const el = document.createElement('div'); el.className = 'day-name'; el.innerText = d; grid.appendChild(el); }});
                
                const firstDay = new Date(year, month, 1).getDay();
                const daysInMonth = new Date(year, month + 1, 0).getDate();
                const startDay = (firstDay + 6) % 7; // 0=Mon, ... 6=Sun
                
                // Start Padding (Only Mon-Fri)
                for(let i=0; i<startDay; i++) {{
                    if(i < 5) grid.appendChild(createEmptyCell());
                }}
                
                let weeklyPnl = 0;
                for(let i=1; i<=daysInMonth; i++) {{
                    const dDateStr = `${{year}}-${{String(month+1).padStart(2, '0')}}-${{String(i).padStart(2, '0')}}`;
                    const dData = dailyData[dDateStr];
                    const dayOfWeek = (startDay + i - 1) % 7; // 0=Mon
                    
                    if(dData) weeklyPnl += dData.pnl;
                    
                    // Render only Mon-Fri (Indices 0-4)
                    if(dayOfWeek < 5) {{
                        const cell = document.createElement('div'); cell.className = 'day-cell';
                        if(dData) {{
                            if(dData.pnl > 0) cell.classList.add('bg-green'); else if(dData.pnl < 0) cell.classList.add('bg-red');
                            cell.innerHTML = `<div class="day-number">${{i}}</div><div><div class="day-pnl ${{(dData.pnl>=0?'positive':'negative')}}">${{dData.pnl < 0 ? '-' : ''}}$${{Math.abs(dData.pnl).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</div><div class="day-trades">${{dData.count}} ${{t('trds')}}</div></div>`;
                            cell.onclick = () => {{ selectedDayKey = dDateStr; switchView('daily'); }};
                        }} else {{ cell.style.opacity = '0.5'; cell.innerHTML = `<div class="day-number">${{i}}</div>`; }}
                        grid.appendChild(cell);
                    }}
                    
                    // End of Week (Sunday=6) -> Append Total
                    if(dayOfWeek === 6) {{ 
                        appendWeeklyTotal(grid, weeklyPnl); 
                        weeklyPnl = 0; 
                    }}
                }}
                
                // End Month Padding
                const endWeekDay = (startDay + daysInMonth - 1) % 7; // 0=Mon
                // If month ends before Sunday, fill remaining Mon-Fri slots then append total
                if (endWeekDay !== 6) {{
                    for(let k=endWeekDay+1; k<5; k++) grid.appendChild(createEmptyCell()); // Fill until Friday
                    appendWeeklyTotal(grid, weeklyPnl);
                }}
                
                renderMonthlyStatsDashboard(monthKey);
                renderGainLossStats(monthKey);
                renderMonthlyTickers(monthKey);
                if (typeof Chart !== 'undefined') {{
                    renderMonthlyEquityChart(monthKey);
                    renderMonthlyBarChart(monthKey);
                }}
            }}

            function createEmptyCell() {{ const d=document.createElement('div'); d.className='day-cell empty'; return d; }}

            function renderMonthlyBarChart(monthKey) {{
                const ctx = document.getElementById('monthlyDailyBarChart').getContext('2d');
                if(monthlyBarChartInstance) monthlyBarChartInstance.destroy();
                
                const [y, m] = monthKey.split('-').map(Number);
                const daysInMonth = new Date(y, m, 0).getDate();
                const labels = [];
                const data = [];
                const bgColors = [];
                
                for(let i=1; i<=daysInMonth; i++) {{
                    const dStr = `${{y}}-${{String(m).padStart(2,'0')}}-${{String(i).padStart(2,'0')}}`;
                    const d = dailyData[dStr];
                    labels.push(i);
                    const val = d ? d.pnl : 0;
                    data.push(val);
                    bgColors.push(val >= 0 ? '#10b981' : '#ef4444');
                }}
                
                monthlyBarChartInstance = new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            label: 'Daily P&L',
                            data: data,
                            backgroundColor: bgColors,
                            borderRadius: 2
                        }}]
                    }},
                    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}, x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ display: false }} }} }} }} 
                }});
            }}

            function renderMonthlyEquityChart(monthKey) {{
                const ctx = document.getElementById('monthlyEquityChart').getContext('2d');
                if(monthlyChartInstance) monthlyChartInstance.destroy();
                
                const data = monthlyEquityData[monthKey] || {{labels: [], data: []}};
                monthlyChartInstance = new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: data.labels,
                        datasets: [{{
                            label: 'Month Equity',
                            data: data.data,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            borderWidth: 2,
                            pointRadius: 2,
                            fill: {{
                                target: 'origin',
                                above: 'rgba(16, 185, 129, 0.1)',
                                below: 'rgba(239, 68, 68, 0.1)'
                            }},
                            tension: 0.1
                        }}]
                    }},
                    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ display: false }} }}, y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }} }} 
                }});
            }}
            
            function renderMonthlyStatsDashboard(monthKey) {{
                const container = document.getElementById('monthlyStatsDashboard');
                const stats = monthlyStats[monthKey];
                const allStats = monthlyGainLoss[monthKey] ? monthlyGainLoss[monthKey].all : null;
                if(!stats || !allStats) {{ container.innerHTML = t('noDataDash'); return; }}
                const mkCard = (title, val, cls='') => `<div><div class="card-title">${{title}}</div><div class="card-value ${{cls}}">${{val}}</div></div>`;
                const netPlClass = allStats.total_pl >= 0 ? 'positive' : 'negative';
                const avgPlClass = allStats.avg_pl >= 0 ? 'positive' : 'negative';
                const avgPctClass = allStats.avg_pct >= 0 ? 'positive' : 'negative';
                container.innerHTML = `
                    ${{mkCard(t('netProfit'), '$'+allStats.total_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), netPlClass)}}
                    ${{mkCard(t('winRate'), stats.win_rate.toFixed(2)+'%')}}
                    ${{mkCard(t('profitFactor'), stats.profit_factor === Infinity ? 'Inf' : stats.profit_factor.toFixed(2))}}
                    ${{mkCard(t('totalTrades'), stats.total_trades)}}
                    ${{mkCard(t('avgPL'), '$'+allStats.avg_pl.toFixed(2), avgPlClass)}}
                    ${{mkCard(t('avgPLPct'), allStats.avg_pct.toFixed(2)+'%', avgPctClass)}}
                `;
            }}
            
            function renderDaily() {{
                const header = document.getElementById('dailyDateTitle');
                const pnlEl = document.getElementById('daily_pnl'); 
                const tradesEl = document.getElementById('daily_trades_count');
                const commEl = document.getElementById('daily_commissions');
                const tbody = document.querySelector('#dailyTradesTable tbody');
                ['d_gl_total_won','d_gl_total_lost','d_gl_avg_won','d_gl_avg_lost','d_gl_pct_won','d_gl_pct_lost','d_gl_count_won','d_gl_count_lost','d_gl_ratio_wl','d_gl_ratio_gp','d_gl_fees','d_gl_max_dd','d_gl_streak_win','d_gl_streak_loss'].forEach(id => document.getElementById(id).innerText = '-');
                tbody.innerHTML = '';
                if(!selectedDayKey) {{ header.innerText = t('selectDayCalendar'); return; }}
                const data = dailyData[selectedDayKey];
                header.innerText = selectedDayKey;
                if(!data) {{ pnlEl.innerText = '-'; commEl.innerText = '-'; return; }}
                pnlEl.innerText = '$' + data.pnl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                pnlEl.className = data.pnl >= 0 ? "card-value positive" : "card-value negative";
                tradesEl.innerText = data.count;
                commEl.innerText = '$' + data.fees.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                const stats = data.stats;
                if(stats) {{
                    ['won','lost'].forEach(t => {{ 
                        const s = stats[t]; 
                        document.getElementById('d_gl_total_'+t).innerText = '$'+s.total_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}); 
                        document.getElementById('d_gl_avg_'+t).innerText = '$'+s.avg_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}); 
                        document.getElementById('d_gl_pct_'+t).innerText = s.avg_pct.toFixed(2)+'%'; 
                        document.getElementById('d_gl_count_'+t).innerText = s.count; 
                    }});
                    const adv = stats.advanced;
                    if(adv) {{
                        const wlRatio = adv.win_loss_ratio;
                        document.getElementById('d_gl_ratio_wl').innerText = t('wlRatio') + ': ' + wlRatio.toFixed(2) + ':1';
                        document.getElementById('d_gl_ratio_wl').className = wlRatio >= 1 ? 'positive' : 'negative';
                        const gpVal = adv.gain_to_pain;
                        document.getElementById('d_gl_ratio_gp').innerText = t('gpRatio') + ': ' + gpVal.toFixed(2) + ':1';
                        document.getElementById('d_gl_ratio_gp').className = gpVal >= 1 ? 'positive' : 'negative';
                        document.getElementById('d_gl_fees').innerText = '$'+data.fees.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                        document.getElementById('d_gl_max_dd').innerText = '$'+adv.max_dd.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                        document.getElementById('d_gl_streak_win').innerHTML = `<div class="positive">${{adv.max_consec_wins}}</div>`;
                        document.getElementById('d_gl_streak_loss').innerHTML = `<div class="negative">${{adv.max_consec_losses}}</div>`;
                    }}
                }}
                // Collect notes from the day's trades
                const notes = [];
                data.trades.forEach(t => {{
                    const tid = t.trade_id || '';
                    const tagData = dailyTags[tid] || {{}};
                    const note = tagData.note || t.note || '';
                    if (note) notes.push(`<strong>${{t.symbol}}</strong>: ${{note}}`);
                }});
                document.getElementById('d_gl_notes').innerHTML = notes.length > 0 ? notes.join('<br>') : '-';
                data.trades.forEach(t => {{
                    const row = document.createElement('tr');
                    const tid = t.trade_id || '';
                    const tagData = dailyTags[tid] || {{}};
                    const entryTag = tagData.entry_tag || t.entry_tag || t.tag || '';
                    const exitTag = tagData.exit_tag || t.exit_tag || '';
                    const tagStyle = 'font-size:0.7rem; padding:2px 6px; border-radius:10px; background:rgba(0,212,255,0.15); color:#00d4ff; white-space:nowrap; display:inline-block; margin:1px;';
                    const tagCell = (tagStr) => {{
                        if (!tagStr) return '';
                        return tagStr.split(',').map(t => t.trim()).filter(Boolean).map(t => `<span style="${{tagStyle}}">${{t}}</span>`).join('');
                    }};
                    row.innerHTML = `<td style="font-weight:bold; color:#60a5fa; cursor:pointer;" onclick="openTagModal('${{tid.replace(/'/g, "\\'")}}', '${{t.symbol}}', '${{t.type}}', ${{t.quantity}}, ${{t.entry}}, ${{t.exit}}, ${{t.pl}})">${{t.symbol}}</td><td>${{t.type}}</td><td>${{t.quantity}}</td><td>$${{t.entry.toFixed(2)}}</td><td>$${{t.exit.toFixed(2)}}</td><td class="${{t.pl >= 0?'positive':'negative'}}">$${{t.pl.toFixed(2)}}</td><td>${{tagCell(entryTag)}}</td><td>${{tagCell(exitTag)}}</td>`;
                    tbody.appendChild(row);
                }});
                if (typeof Chart !== 'undefined') renderDailyEquityChart(selectedDayKey);
            }}

            function openTagModal(tradeId, symbol, dir, qty, entry, exit, pl) {{
                document.getElementById('modalTitle').innerText = symbol + ' — ' + dir;
                document.getElementById('modalSymbol').innerText = symbol;
                document.getElementById('modalDir').innerText = dir;
                document.getElementById('modalQty').innerText = qty;
                document.getElementById('modalEntry').innerText = '$' + entry.toFixed(4);
                document.getElementById('modalExit').innerText = '$' + exit.toFixed(4);
                const plEl = document.getElementById('modalPnL');
                plEl.innerText = '$' + pl.toFixed(2);
                plEl.className = pl >= 0 ? 'positive' : 'negative';

                // Load existing tags
                const existing = dailyTags[tradeId] || {{}};
                document.getElementById('entryTagInput').value = existing.entry_tag || '';
                document.getElementById('exitTagInput').value = existing.exit_tag || '';
                document.getElementById('noteInput').value = existing.note || '';

                // Load custom presets from localStorage
                let customEntry = [];
                let customExit = [];
                try {{
                    customEntry = JSON.parse(localStorage.getItem('customEntryPresets') || '[]');
                    customExit = JSON.parse(localStorage.getItem('customExitPresets') || '[]');
                }} catch(e) {{}}

                // Standard presets
                const stdPresets = ['Momentum', 'Breakout', 'Reversal', 'News', 'Scalp', 'Swing', 'Pullback', 'Trend Follow', 'Fade', 'Gap', 'VWAP', 'Support', 'Resistance'];

                ['entryTagPresets', 'exitTagPresets'].forEach(containerId => {{
                    const container = document.getElementById(containerId);
                    container.innerHTML = '';
                    const inputId = containerId === 'entryTagPresets' ? 'entryTagInput' : 'exitTagInput';
                    const customs = containerId === 'entryTagPresets' ? customEntry : customExit;

                    // Show custom presets first (with remove hint)
                    customs.forEach(tag => {{
                        const btn = document.createElement('button');
                        btn.innerText = tag;
                        btn.style.cssText = 'background:rgba(0,212,255,0.25); color:#fff; border:1px solid var(--accent-primary); padding:4px 10px; border-radius:12px; cursor:pointer; font-size:0.75rem;';
                        btn.onmouseenter = () => {{ btn.style.background = 'rgba(0,212,255,0.5)'; }};
                        btn.onmouseleave = () => {{ btn.style.background = 'rgba(0,212,255,0.25)'; }};
                        btn.onclick = () => {{
                            const cur = document.getElementById(inputId).value;
                            const tags = cur ? cur.split(',').map(s => s.trim()).filter(Boolean) : [];
                            if (!tags.includes(tag)) {{
                                tags.push(tag);
                                document.getElementById(inputId).value = tags.join(', ');
                            }}
                        }};
                        container.appendChild(btn);
                    }});

                    // Standard presets
                    stdPresets.forEach(tag => {{
                        const btn = document.createElement('button');
                        btn.innerText = tag;
                        btn.style.cssText = 'background:rgba(0,212,255,0.1); color:var(--text-primary); border:1px solid var(--border-color); padding:4px 10px; border-radius:12px; cursor:pointer; font-size:0.75rem;';
                        btn.onmouseenter = () => {{ btn.style.background = 'rgba(0,212,255,0.3)'; }};
                        btn.onmouseleave = () => {{ btn.style.background = 'rgba(0,212,255,0.1)'; }};
                        btn.onclick = () => {{
                            const cur = document.getElementById(inputId).value;
                            const tags = cur ? cur.split(',').map(s => s.trim()).filter(Boolean) : [];
                            if (!tags.includes(tag)) {{
                                tags.push(tag);
                                document.getElementById(inputId).value = tags.join(', ');
                            }}
                        }};
                        container.appendChild(btn);
                    }});
                }});

                // Store current trade ID for save
                document.getElementById('tagModal')._tradeId = tradeId;
                document.getElementById('tagModal').style.display = 'flex';
            }}

            function closeTagModal() {{
                document.getElementById('tagModal').style.display = 'none';
            }}

            function saveTagEntry() {{
                const tradeId = document.getElementById('tagModal')._tradeId;
                if (!tradeId) return;
                const entryTag = document.getElementById('entryTagInput').value.trim();
                const exitTag = document.getElementById('exitTagInput').value.trim();
                const note = document.getElementById('noteInput').value.trim();

                // Update in-memory tags
                if (entryTag || exitTag || note) {{
                    dailyTags[tradeId] = {{ entry_tag: entryTag, exit_tag: exitTag, note: note }};
                }} else {{
                    delete dailyTags[tradeId];
                }}

                // Save custom presets from comma-separated tags
                try {{
                    const extractTags = (str) => str ? str.split(',').map(s => s.trim()).filter(Boolean) : [];
                    const allEntry = extractTags(entryTag);
                    const allExit = extractTags(exitTag);
                    const stdPresets = ['Momentum', 'Breakout', 'Reversal', 'News', 'Scalp', 'Swing', 'Pullback', 'Trend Follow', 'Fade', 'Gap', 'VWAP', 'Support', 'Resistance'];
                    const isCustom = t => !stdPresets.includes(t);

                    const saveCustom = (key, tags) => {{
                        let existing = [];
                        try {{ existing = JSON.parse(localStorage.getItem(key) || '[]'); }} catch(e) {{}}
                        tags.filter(isCustom).forEach(t => {{ if (!existing.includes(t)) existing.push(t); }});
                        if (existing.length > 30) existing = existing.slice(-30);
                        localStorage.setItem(key, JSON.stringify(existing));
                    }};
                    saveCustom('customEntryPresets', allEntry);
                    saveCustom('customExitPresets', allExit);
                }} catch(e) {{}}

                // Update localStorage backup
                try {{ localStorage.setItem('tradingTags', JSON.stringify(dailyTags)); }} catch(e) {{}}

                // Recompute tag metrics from live data
                refreshTagMetrics();

                closeTagModal();
                // Re-render current views
                if (selectedDayKey) renderDaily();
                if (currentView === 'ratios') renderRatios();
            }}

            function refreshTagMetrics() {{
                // Rebuild tag data per month from dailyData + dailyTags
                const byMonth = {{}};
                for (const [dayKey, dayData] of Object.entries(dailyData)) {{
                    if (!dayData || !dayData.trades) continue;
                    const monthKey = dayKey.substring(0, 7);
                    if (!byMonth[monthKey]) byMonth[monthKey] = {{}};
                    dayData.trades.forEach(t => {{
                        const tid = t.trade_id || '';
                        const tagData = dailyTags[tid] || {{}};
                        const entryTagRaw = tagData.entry_tag || t.entry_tag || t.tag || '';
                        const entryTags = entryTagRaw ? entryTagRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
                        const tagNames = entryTags.length > 0 ? entryTags : ['Untagged'];
                        const tradeInfo = {{
                            symbol: t.symbol,
                            dir: t.type,
                            qty: t.quantity,
                            entry: t.entry,
                            exit: t.exit,
                            pl: t.pl,
                            date: t.close_date,
                            exit_tag: tagData.exit_tag || t.exit_tag || '',
                            note: tagData.note || t.note || ''
                        }};
                        // Add trade to each of its tags
                        tagNames.forEach(tagName => {{
                            if (!byMonth[monthKey][tagName]) byMonth[monthKey][tagName] = [];
                            byMonth[monthKey][tagName].push(tradeInfo);
                        }});
                    }});
                }}

                // Update monthlyGainLoss tags
                for (const [monthKey, tagMap] of Object.entries(byMonth)) {{
                    if (!monthlyGainLoss[monthKey]) continue;
                    const newTags = [];
                    for (const [tagName, trades] of Object.entries(tagMap)) {{
                        const count = trades.length;
                        const wins = trades.filter(t => t.pl > 0);
                        const winRate = count > 0 ? (wins.length / count * 100) : 0;
                        const totalPl = trades.reduce((sum, t) => sum + t.pl, 0);
                        const avgPl = count > 0 ? totalPl / count : 0;
                        trades.sort((a, b) => a.date.localeCompare(b.date));
                        newTags.push({{
                            tag: tagName,
                            count: count,
                            win_rate: winRate,
                            avg_pl: avgPl,
                            trades: trades
                        }});
                    }}
                    newTags.sort((a, b) => b.count - a.count);
                    monthlyGainLoss[monthKey].tags = newTags;
                }}
            }}

            function saveTagsToFile() {{
                const jsonStr = JSON.stringify(dailyTags, null, 2);
                // Try to save via local server first (more automatic)
                if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {{
                    fetch('/save-tags', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: jsonStr
                    }}).then(r => r.json()).then(data => {{
                        if (data.ok) {{
                            showSaveToast('Tags saved!');
                        }} else {{
                            downloadTagsFile(jsonStr);
                        }}
                    }}).catch(() => downloadTagsFile(jsonStr));
                }} else {{
                    downloadTagsFile(jsonStr);
                }}
                try {{ localStorage.setItem('tradingTags', JSON.stringify(dailyTags)); }} catch(e) {{}}
            }}

            function downloadTagsFile(jsonStr) {{
                const blob = new Blob([jsonStr], {{type: 'application/json'}});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'tags.json';
                a.click();
                URL.revokeObjectURL(url);
                showSaveToast('tags.json downloaded — place it in Reportes_Brokers/');
            }}

            function showSaveToast(msg) {{
                const toast = document.createElement('div');
                toast.innerText = msg;
                toast.style.cssText = 'position:fixed; bottom:2rem; right:2rem; background:#00d4ff; color:#000; padding:0.75rem 1.5rem; border-radius:12px; font-weight:600; z-index:99999; animation:fadeOut 2s forwards;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2500);
            }}

            // Restore tags from localStorage on load (survives page refreshes without re-download)
            try {{
                const saved = localStorage.getItem('tradingTags');
                if (saved) {{
                    const parsed = JSON.parse(saved);
                    Object.assign(dailyTags, parsed);
                    // Recompute tag metrics with restored tags
                    setTimeout(refreshTagMetrics, 100);
                }}
            }} catch(e) {{}}

            function renderDailyEquityChart(dayKey) {{
                const ctx = document.getElementById('dailyEquityChart').getContext('2d');
                if(dailyChartInstance) dailyChartInstance.destroy();
                const data = dailyEquityData[dayKey] || {{labels: [], data: []}};
                dailyChartInstance = new Chart(ctx, {{
                    type: 'line',
                    data: {{ labels: data.labels, datasets: [{{ label: 'Day Equity', data: data.data, borderColor: '#a855f7', backgroundColor: 'rgba(168, 85, 247, 0.1)', borderWidth: 2, pointRadius: 2, fill: true, tension: 0.1 }}] }},
                    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display:false }}, y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }} }} }} 
                }});
            }}

            function renderGainLossStats(monthKey) {{
                const fmt = (val) => val === undefined ? '-' : '$' + val.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                const fmtPct = (val) => val === undefined ? '-' : val.toFixed(2) + '%';
                document.getElementById('glStatsMonthLabel').innerText = `(${{monthKey}})`;
                const stats = monthlyGainLoss[monthKey];
                const types = ['won','lost'];
                ['gl_streak_win','gl_streak_loss'].forEach(id => document.getElementById(id).innerText = '-');
                if(!stats) {{ types.forEach(t=>{{ document.getElementById('gl_total_'+t).innerText='-'; document.getElementById('gl_avg_'+t).innerText='-'; document.getElementById('gl_pct_'+t).innerText='-'; document.getElementById('gl_count_'+t).innerText='-'; }}); return; }}
                types.forEach(t => {{ const s = stats[t]; document.getElementById('gl_total_'+t).innerText = fmt(s.total_pl); document.getElementById('gl_avg_'+t).innerText = fmt(s.avg_pl); document.getElementById('gl_pct_'+t).innerText = fmtPct(s.avg_pct); document.getElementById('gl_count_'+t).innerText = s.count; }});
                const adv = stats.advanced;
                if(adv) {{
                    document.getElementById('gl_streak_win').innerHTML = `<div class="positive">${{adv.max_consec_wins}} <span style="font-size:0.7rem; color:var(--text-secondary)">(${{adv.max_consec_wins_dates}})</span></div>`;
                    document.getElementById('gl_streak_loss').innerHTML = `<div class="negative">${{adv.max_consec_losses}} <span style="font-size:0.7rem; color:var(--text-secondary)">(${{adv.max_consec_losses_dates}})</span></div>`;
                }}
                if(stats.expenses !== undefined) {{
                    document.getElementById('gl_expenses').innerText = '$' + stats.expenses.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                }}
            }}

            function renderMonthlyTickers(monthKey) {{
                const tbody = document.querySelector('#monthlyTickersTable tbody');
                tbody.innerHTML = '';
                document.getElementById('tickerMonthLabel').innerText = `(${{monthKey}})`;
                const symbols = monthlySymbols[monthKey] || [];
                if (symbols.length === 0) {{ tbody.innerHTML = '<tr><td colspan="3">No Data</td></tr>'; return; }}
                symbols.forEach(s => {{ const row = document.createElement('tr'); const plClass = s.pnl >= 0 ? 'positive' : 'negative'; row.innerHTML = `<td style="font-weight:bold; color:#60a5fa;">${{s.symbol}}</td><td>${{s.count}}</td><td class="${{plClass}}">$${{Math.abs(s.pnl).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>`; tbody.appendChild(row); }});
            }}

            function createEmptyCell() {{ const d=document.createElement('div'); d.className='day-cell empty'; return d; }}
            
            function renderRatios() {{
                const year = currentDate.getFullYear();
                const month = currentDate.getMonth();
                const monthKey = `${{year}}-${{String(month + 1).padStart(2, '0')}}`;
                document.getElementById('ratiosTitle').innerText = `${{getMonthName(month)}} ${{year}}`;
                
                const container = document.getElementById('ratiosGrid');
                container.innerHTML = '';
                
                const basicStats = monthlyStats[monthKey];
                const stats = monthlyGainLoss[monthKey];
                
                if(!basicStats || !stats) {{ container.innerHTML = '<div class="card">No Data</div>'; return; }}
                
                const mkCard = (title, val, cls='') => `<div class="card" style="height: 80px; padding: 0.5rem; display: flex; flex-direction: column; overflow: hidden; position: relative;"><div class="card-title" style="margin-bottom:0; position:relative; z-index:10;">${{title}}</div><div class="card-value ${{cls}}" style="flex-grow: 1; display: flex; align-items: center; justify-content: flex-start; font-size: 1.5rem; position:relative; z-index:10;">${{val}}</div></div>`;
                const adv = stats.advanced;
                
                let html = '';
                const netPl = stats.all ? stats.all.total_pl : 0;
                const netPlCls = netPl >= 0 ? 'positive' : 'negative';
                html += mkCard('Net Profit', '$' + netPl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), netPlCls);
                
                const totalTrades = stats.all ? stats.all.count : 0;
                html += mkCard('Total Trades', totalTrades);
                
                const winCount = stats.won ? stats.won.count : 0;
                const lossCount = stats.lost ? stats.lost.count : 0;
                
                let winValuesRatio = "N/A";
                if (lossCount > 0) {{
                    const ratio = winCount / lossCount;
                    winValuesRatio = ratio.toFixed(2) + ":1";
                }} else if (winCount > 0) {{
                    winValuesRatio = winCount + ":0";
                }}
                
                html += mkCard('Win Rate (W:1)', winValuesRatio);
                
                if (adv) {{
                    const avgWin = adv.avg_win || 0;
                    const avgLoss = Math.abs(adv.avg_loss || 0);
                    const wlDollarRatio = avgLoss > 0 ? (avgWin / avgLoss) : 0;
                    const wlCls = wlDollarRatio >= 1 ? 'positive' : 'negative';
                    const wlVal = '$' + wlDollarRatio.toFixed(2) + ':1';
                    html += mkCard('Avg Win / Loss', wlVal, wlCls);
                }}
                
                const winPct = totalTrades > 0 ? (winCount / totalTrades * 100) : 0.0;
                const lossPct = totalTrades > 0 ? (lossCount / totalTrades * 100) : 0.0;
                
                html += mkCard('Winning Trades', `${{winCount}} <span style="font-size:0.9rem; margin-left: 12px;">(${{winPct.toFixed(2)}}%)</span>`, 'positive');
                html += mkCard('Losing Trades', `${{lossCount}} <span style="font-size:0.9rem; margin-left: 12px;">(${{lossPct.toFixed(2)}}%)</span>`, 'negative');
                
                // Replaced Profit Factor with Long/Short Chart
                // Adjusted height to be more compact (80px to match standard cards)
                html += '<div class="card" style="height: 80px; padding: 0.5rem; display: flex; flex-direction: column;"><div class="card-title" style="margin-bottom: 0.25rem;">Long vs Short</div><div class="chart-container" style="flex-grow: 1; height: 0; min-height: 0; position: relative;"><canvas id="longShortChart"></canvas></div></div>';
                
                if(adv) {{
                    
                    
                    const gpVal = adv.gain_to_pain;
                    const gpCls = gpVal >= 1 ? 'positive' : 'negative';
                    const gpDisplay = gpVal === Infinity ? 'Inf' : gpVal.toFixed(2) + ':1';
                    html += mkCard('Gain / Pain Ratio', gpDisplay, gpCls);
                    
                    html += mkCard('Expectancy', '$'+adv.expectancy.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), adv.expectancy>=0?'positive':'negative');
                    html += mkCard('Max Drawdown', '$'+adv.max_dd.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), 'negative');
                    html += mkCard('Max Consec Wins', adv.max_consec_wins, 'positive');
                    html += mkCard('Max Consec Losses', adv.max_consec_losses, 'negative');

                    // --- NEW RATIOS FROM MARKDOWN ---
                    html += '<div style="grid-column: 1 / -1; margin-top: 1rem; border-top: 1px solid var(--border-color); padding-top: 1rem;"><h3 style="color: var(--accent-primary); font-size: 0.9rem;">Advanced Performance Ratios</h3></div>';
                    
                    // Core Performance
                    html += mkCard('Edge Score', adv.edge_score.toFixed(2), adv.edge_score >= 0 ? 'positive' : 'negative');
                    html += mkCard('Recovery Factor', adv.recovery_factor.toFixed(2), adv.recovery_factor >= 1.5 ? 'positive' : '');
                    html += mkCard('Payoff Ratio', adv.payoff_ratio.toFixed(2) + ':1', adv.payoff_ratio >= 1.5 ? 'positive' : '');
                    html += mkCard('Calmar Ratio', adv.calmar.toFixed(2), adv.calmar >= 1.5 ? 'positive' : '');
                    
                    // Risk Adjusted
                    html += mkCard('Sharpe Ratio', adv.sharpe.toFixed(2), adv.sharpe >= 1 ? 'positive' : '');
                    html += mkCard('Sortino Ratio', adv.sortino.toFixed(2), adv.sortino >= 1 ? 'positive' : '');
                    html += mkCard('SQN', adv.sqn.toFixed(2), adv.sqn >= 2 ? 'positive' : '');
                    html += mkCard('Consistency Ratio', adv.consistency_ratio.toFixed(2), adv.consistency_ratio >= 0.1 ? 'positive' : '');
                    html += mkCard('Z-Score', adv.z_score.toFixed(2), Math.abs(adv.z_score) >= 1.96 ? 'positive' : '');
                    
                    // Efficiency
                    html += mkCard('Profit Factor (L)', adv.pf_long === Infinity ? 'Inf' : adv.pf_long.toFixed(2), adv.pf_long >= 1 ? 'positive' : 'negative');
                    html += mkCard('Profit Factor (S)', adv.pf_short === Infinity ? 'Inf' : adv.pf_short.toFixed(2), adv.pf_short >= 1 ? 'positive' : 'negative');
                    html += mkCard('Win Rate (L)', adv.wr_long.toFixed(1) + '%', adv.wr_long >= 50 ? 'positive' : '');
                    html += mkCard('Win Rate (S)', adv.wr_short.toFixed(1) + '%', adv.wr_short >= 50 ? 'positive' : '');
                    html += mkCard('Trades per Day', adv.trades_per_day.toFixed(1));

                    // Drawdown & Recovery
                    html += mkCard('Max DD Duration', adv.max_dd_duration + ' Days', 'negative');
                    html += mkCard('Equity Peak', '$' + adv.equity_peak.toLocaleString(undefined, {{maximumFractionDigits: 0}}), 'positive');
                    
                    // Streaks & Consistency
                    html += mkCard('Std Dev P&L', '$' + adv.std_dev.toLocaleString(undefined, {{maximumFractionDigits: 0}}));
                    html += mkCard('Standard Error', adv.standard_error.toFixed(2));
                    html += mkCard('T-Score', adv.t_score.toFixed(2), adv.t_score >= 2 ? 'positive' : '');

                    // Time Analysis
                    html += mkCard('Avg Time Win', adv.avg_time_win.toFixed(1) + ' Days');

                    // Capital Allocation
                    html += mkCard('Kelly Criterion', adv.kelly.toFixed(2) + '%', adv.kelly > 0 ? 'positive' : 'negative');
                }}
                
                // New KPIs requested
                if (stats.traded_days !== undefined) {{
                    html += mkCard('Traded Days', stats.traded_days);
                    html += mkCard('Trading Commissions', '$' + basicStats.fees.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), 'negative');
                    html += mkCard('Fixed Expenses', '$' + stats.expenses.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), 'negative');
                    const avgDailyCls = stats.avg_daily_pl >= 0 ? 'positive' : 'negative';
                    html += mkCard('Avg Daily P&L', '$' + stats.avg_daily_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}), avgDailyCls);
                }}

                if(stats.tags && stats.tags.length > 0) {{
                    html += '<div style="grid-column: 1 / -1; margin-top: 2rem; display: grid; grid-template-columns: 2fr 1fr; gap: 1rem;">';

                    // Tag Performance Table (2/3 width) — expandable
                    html += '<div>';
                    html += '<h3 style="margin-bottom: 1rem; color: var(--text-secondary);">Tag Performance</h3>';
                    html += '<div class="card" style="padding: 0; overflow: hidden;">';
                    html += '<table style="width: 100%; text-align: left;">';
                    html += '<thead><tr><th>Tag</th><th>Count</th><th>Win Rate</th><th>Avg P&L</th></tr></thead>';
                    html += '<tbody>';
                    stats.tags.forEach((t, i) => {{
                        const winRateCls = t.win_rate >= 50 ? 'positive' : (t.win_rate < 40 ? 'negative' : '');
                        const avgPlCls = t.avg_pl >= 0 ? 'positive' : 'negative';
                        const tagId = 'tag_' + i + '_' + monthKey;
                        html += `<tr style="cursor:pointer;" onclick="document.getElementById('${{tagId}}').style.display = document.getElementById('${{tagId}}').style.display === 'none' ? '' : 'none'">
                            <td style="font-weight: 600; color:#60a5fa;">&#9654; ${{t.tag}}</td>
                            <td>${{t.count}}</td>
                            <td class="${{winRateCls}}">${{t.win_rate.toFixed(2)}}%</td>
                            <td class="${{avgPlCls}}">$${{t.avg_pl.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
                        </tr>`;
                        // Expandable trades list
                        html += `<tr id="${{tagId}}" style="display:none;"><td colspan="4" style="padding:0; background:rgba(0,0,0,0.3);">
                            <table style="width:100%; font-size:0.8rem; margin:0;">
                                <thead><tr style="color:var(--text-secondary);">
                                    <th>Symbol</th><th>Dir</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Exit Tag</th><th>Note</th>
                                </tr></thead>
                                <tbody>`;
                        (t.trades || []).forEach(tr => {{
                            const plCls = tr.pl >= 0 ? 'positive' : 'negative';
                            html += `<tr>
                                <td style="font-weight:bold; color:#60a5fa;">${{tr.symbol}}</td>
                                <td>${{tr.dir}}</td>
                                <td>${{tr.qty}}</td>
                                <td>$${{tr.entry.toFixed(4)}}</td>
                                <td>$${{tr.exit.toFixed(4)}}</td>
                                <td class="${{plCls}}">$${{tr.pl.toFixed(2)}}</td>
                                <td style="color:#94a3b8;">${{tr.exit_tag || '-'}}</td>
                                <td style="color:#94a3b8;">${{tr.note || '-'}}</td>
                            </tr>`;
                        }});
                        html += '</tbody></table></td></tr>';
                    }});
                    html += '</tbody></table></div></div>';
                    
                    // Weekday Performance Table (1/3 width)
                    if (stats.weekdays) {{
                        html += '<div>';
                        html += '<h3 style="margin-bottom: 1rem; color: var(--text-secondary);">Weekday Performance</h3>';
                        html += '<div class="card" style="padding: 0; overflow: hidden; height: 100%;">';
                        html += '<table style="width: 100%; text-align: left;">';
                        html += '<thead><tr><th>Day</th><th>Count</th><th>Total P&L</th><th>Win Rate</th></tr></thead>';
                        html += '<tbody>';
                        stats.weekdays.forEach(d => {{
                            const totalPlCls = d.total_pl >= 0 ? 'positive' : 'negative';
                            const winRateCls = d.win_rate >= 50 ? 'positive' : (d.win_rate < 40 ? 'negative' : '');
                            html += `<tr>
                                <td style="font-weight: 600;">${{d.day_name}}</td>
                                <td>${{d.count}}</td>
                                <td class="${{totalPlCls}}">$${{d.total_pl.toLocaleString(undefined, {{minimumFractionDigits: 0, maximumFractionDigits: 0}})}}</td>
                                <td class="${{winRateCls}}">${{d.win_rate.toFixed(1)}}%</td>
                            </tr>`;
                        }});
                        html += '</tbody></table></div></div>';
                    }}
                    
                    html += '</div>'; // End grid container
                }}
                
                container.innerHTML = html;
                
                // Render Chart
                if (typeof Chart !== 'undefined' && basicStats) {{
                    const ctx = document.getElementById('longShortChart').getContext('2d');
                    if (longShortChartInstance) longShortChartInstance.destroy();
                    
                    const total = basicStats.long_count + basicStats.short_count;
                    const longPct = total > 0 ? (basicStats.long_count / total * 100).toFixed(1) + '%' : '0%';
                    const shortPct = total > 0 ? (basicStats.short_count / total * 100).toFixed(1) + '%' : '0%';
                    
                    longShortChartInstance = new Chart(ctx, {{
                        type: 'doughnut',
                        data: {{
                            labels: [`Long (${{longPct}})`, `Short (${{shortPct}})`],
                            datasets: [{{
                                data: [basicStats.long_count, basicStats.short_count],
                                backgroundColor: ['#10b981', '#ef4444'], // Green for Long, Red for Short
                                borderWidth: 0
                            }}]
                        }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                legend: {{ position: 'right', labels: {{ color: '#94a3b8', boxWidth: 10, font: {{ size: 10 }} }} }}
                            }},
                             cutout: '50%'
                        }}
                    }});
                }}
            }}

            function appendWeeklyTotal(grid, pnl) {{ const d=document.createElement('div'); d.className='week-total'; d.innerHTML = `<div class="week-label">Week</div><div class="${{pnl>=0?'positive':'negative'}}" style="font-weight:700;">$${{Math.abs(pnl).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</div>`; grid.appendChild(d); }}
            function toggleCustomizer() {{
                const sidebar = document.getElementById('customizerSidebar');
                if (sidebar.style.right === '0px') {{
                    sidebar.style.right = '-400px';
                }} else {{
                    sidebar.style.right = '0px';
                }}
            }}

            function updateAccent(color) {{
                document.documentElement.style.setProperty('--accent-primary', color);
                document.documentElement.style.setProperty('--border-color', color + '4D'); // 30% alpha
                document.documentElement.style.setProperty('--accent-primary-dim', color + '26'); // 15% alpha
                document.getElementById('accentHex').innerText = color.toUpperCase();
                document.getElementById('accentPicker').value = color;
                
                // Update dynamic shadows
                document.documentElement.style.setProperty('--border-glow', `0 0 10px ${{color}}33, inset 0 0 10px ${{color}}1A`);
                
                localStorage.setItem('midge_theme_accent', color);
            }}

            function applyPreset(color) {{
                updateAccent(color);
            }}

            function updateGrid(val) {{
                const alpha = (val / 100).toFixed(2);
                const bgSVG = document.querySelector('.circuit-bg');
                if (bgSVG) bgSVG.style.opacity = alpha;
                
                // Update CSS var for other things that might use it
                const color = getComputedStyle(document.documentElement).getPropertyValue('--accent-primary').trim();
                document.documentElement.style.setProperty('--accent-primary-dim', color + Math.round(val * 2.55).toString(16).padStart(2, '0'));
                localStorage.setItem('midge_theme_grid', val);
            }}

            function updateMode(mode) {{
                if (mode === 'light') {{
                    document.documentElement.style.setProperty('--bg-color', '#f1f5f9');
                    document.documentElement.style.setProperty('--card-bg', 'rgba(255, 255, 255, 0.8)');
                    document.documentElement.style.setProperty('--text-primary', '#0f172a');
                    document.documentElement.style.setProperty('--text-secondary', '#64748b');
                    document.getElementById('modeLight').classList.add('active');
                    document.getElementById('modeDark').classList.remove('active');
                }} else {{
                    document.documentElement.style.setProperty('--bg-color', '#030712');
                    document.documentElement.style.setProperty('--card-bg', 'rgba(3, 7, 18, 0.7)');
                    document.documentElement.style.setProperty('--text-primary', '#e2e8f0');
                    document.documentElement.style.setProperty('--text-secondary', '#94a3b8');
                    document.getElementById('modeDark').classList.add('active');
                    document.getElementById('modeLight').classList.remove('active');
                }}
                localStorage.setItem('midge_theme_mode', mode);
            }}

            function resetTheme() {{
                localStorage.removeItem('midge_theme_accent');
                localStorage.removeItem('midge_theme_grid');
                localStorage.removeItem('midge_theme_mode');
                location.reload();
            }}

            // Load saved theme
            window.addEventListener('DOMContentLoaded', () => {{
                const savedAccent = localStorage.getItem('midge_theme_accent');
                const savedGrid = localStorage.getItem('midge_theme_grid');
                const savedMode = localStorage.getItem('midge_theme_mode');

                if (savedAccent) updateAccent(savedAccent);
                if (savedGrid) {{
                    document.getElementById('gridSlider').value = savedGrid;
                    updateGrid(savedGrid);
                }}
                if (savedMode) updateMode(savedMode);
            }});

            function changeMonth(delta) {{
                currentDate.setMonth(currentDate.getMonth() + delta);
                if(currentView === 'monthly') renderCalendar();
                if(currentView === 'ratios') renderRatios();
            }}

            // ===== BUILD REPORT FUNCTIONS =====
            let buildReportInitialized = false;
            let _allTradesFlat = null;

            function getAllTrades() {{
                if (_allTradesFlat) return _allTradesFlat;
                _allTradesFlat = [];
                Object.keys(dailyData).forEach(dateKey => {{
                    const day = dailyData[dateKey];
                    if (day && day.trades) {{
                        day.trades.forEach(t => {{
                            _allTradesFlat.push({{ ...t, _date: dateKey }});
                        }});
                    }}
                }});
                return _allTradesFlat;
            }}

            function getUniqueTags() {{
                const tags = new Set();
                getAllTrades().forEach(t => {{
                    (t.tag || '').split(',').map(s => s.trim()).filter(Boolean).forEach(tag => tags.add(tag));
                    (t.entry_tag || '').split(',').map(s => s.trim()).filter(Boolean).forEach(tag => tags.add(tag));
                    (t.exit_tag || '').split(',').map(s => s.trim()).filter(Boolean).forEach(tag => tags.add(tag));
                }});
                return [...tags].sort();
            }}

            const brTags = {{ a: [], b: [] }};

            function toggleTagDropdown(group) {{
                const dd = document.getElementById('br-tags-dropdown-' + group);
                document.querySelectorAll('.br-tag-dropdown').forEach(el => {{
                    if (el.id !== dd.id) el.classList.remove('show');
                }});
                dd.classList.toggle('show');
            }}

            function buildTagOptions(group) {{
                const dd = document.getElementById('br-tags-dropdown-' + group);
                const allTags = getUniqueTags();
                if (allTags.length === 0) {{
                    dd.innerHTML = '<div class="br-tag-option" style="color:var(--text-secondary);">No tags found</div>';
                    return;
                }}
                dd.innerHTML = '';
                allTags.forEach(tag => {{
                    const opt = document.createElement('div');
                    opt.className = 'br-tag-option';
                    opt.innerHTML = (brTags[group].includes(tag) ? '&#x2713; ' : '') + tag;
                    opt.onclick = (e) => {{ e.stopPropagation(); toggleTag(group, tag); }};
                    dd.appendChild(opt);
                }});
            }}

            function toggleTag(group, tag) {{
                const idx = brTags[group].indexOf(tag);
                if (idx > -1) brTags[group].splice(idx, 1);
                else brTags[group].push(tag);
                buildTagOptions(group);
                renderTagChips(group);
                updateBuildCounts();
            }}

            function renderTagChips(group) {{
                const chips = document.getElementById('br-tags-chips-' + group);
                const ph = document.getElementById('br-tags-placeholder-' + group);
                chips.innerHTML = '';
                const sel = brTags[group];
                if (sel.length === 0) {{ ph.style.display = 'inline'; return; }}
                ph.style.display = 'none';
                sel.forEach(tag => {{
                    const chip = document.createElement('span');
                    chip.className = 'br-tag-chip';
                    chip.innerHTML = tag + ' <span class="remove" onclick="event.stopPropagation(); toggleTag(\\'' + group + '\\',\\'' + tag + '\\')">&times;</span>';
                    chips.appendChild(chip);
                }});
            }}

            function getDateInputs(group) {{
                const fe = document.getElementById('br-datefrom-' + group);
                const te = document.getElementById('br-dateto-' + group);
                return {{
                    start: fe && fe.value ? new Date(fe.value + 'T00:00:00') : null,
                    end: te && te.value ? new Date(te.value + 'T23:59:59') : null
                }};
            }}

            function filterTrades(group) {{
                const sv = document.getElementById('br-symbol-' + group).value.toUpperCase().trim();
                const symbols = sv ? sv.split(',').map(s => s.trim()).filter(Boolean) : [];
                const side = document.getElementById('br-side-' + group).value;
                const dur = document.getElementById('br-duration-' + group).value;
                const pf = document.getElementById('br-pnl-' + group).value;
                const dr = getDateInputs(group);
                const st = brTags[group];
                return getAllTrades().filter(t => {{
                    if (symbols.length && !symbols.includes(t.symbol.toUpperCase())) return false;
                    if (side !== 'all' && t.type !== side) return false;
                    if (pf === 'winning' && t.pl <= 0) return false;
                    if (pf === 'losing' && t.pl >= 0) return false;
                    if (pf === 'breakeven' && Math.abs(t.pl) > 0.01) return false;
                    if (dur === 'day' && t.close_date && t._date && t.close_date !== t._date) return false;
                    if (dur === 'swing' && t.close_date && t._date && t.close_date === t._date) return false;
                    if (dr.start && dr.end) {{ const td = new Date(t._date); if (td < dr.start || td > dr.end) return false; }}
                    if (st.length) {{
                        const tt = new Set();
                        (t.tag||'').split(',').map(s=>s.trim()).filter(Boolean).forEach(x=>tt.add(x));
                        (t.entry_tag||'').split(',').map(s=>s.trim()).filter(Boolean).forEach(x=>tt.add(x));
                        (t.exit_tag||'').split(',').map(s=>s.trim()).filter(Boolean).forEach(x=>tt.add(x));
                        if (!st.some(x => tt.has(x))) return false;
                    }}
                    return true;
                }});
            }}

            function computeMetrics(trades) {{
                const n = trades.length;
                if (!n) return null;
                const tp = trades.reduce((s,t) => s + t.pl, 0);
                const w = trades.filter(t => t.pl > 0.01);
                const l = trades.filter(t => t.pl < -0.01);
                const wc = w.length, lc = l.length;
                const dm = {{}};
                trades.forEach(t => {{ const d = t._date; if (!dm[d]) dm[d] = {{p:0,c:0}}; dm[d].p += t.pl; dm[d].c++; }});
                const dk = Object.keys(dm);
                const dp = dk.map(d => dm[d].p);
                const adp = dk.length ? dp.reduce((s,v)=>s+v,0)/dk.length : 0;
                const adv = dk.length ? dk.reduce((s,d)=>s+dm[d].c,0)/dk.length : 0;
                const sh = trades.reduce((s,t) => s + t.quantity, 0);
                const aps = sh ? tp/sh : 0;
                const aw = wc ? w.reduce((s,t)=>s+t.pl,0)/wc : 0;
                const al = lc ? l.reduce((s,t)=>s+t.pl,0)/lc : 0;
                const mn = tp/n;
                const sd = Math.sqrt(trades.reduce((s,t) => s + Math.pow(t.pl - mn, 2), 0) / n);
                const zs = sd > 0 ? (mn/sd)*Math.sqrt(n) : 0;
                const pr = Math.min(100, Math.max(0, (1 - 0.5*(1 + erf(Math.abs(zs)/Math.sqrt(2))))*100));
                const cum = []; let rn = 0;
                trades.forEach(t => {{ rn += t.pl; cum.push(rn); }});
                const n2 = cum.length;
                let sx=0,sy=0,sxx=0,sxy=0;
                cum.forEach((y,i) => {{ sx+=i; sy+=y; sxx+=i*i; sxy+=i*y; }});
                const denom = n2*sxx - sx*sx;
                const sl = denom ? (n2*sxy - sx*sy)/denom : 0;
                const yh = cum.map((y,i) => sl*i + (sy-sl*sx)/n2);
                const rs = cum.map((y,i) => Math.pow(y-yh[i],2)).reduce((s,r)=>s+r,0);
                const se = (n2>2 && denom/n2>0) ? Math.sqrt(rs/(n2-2))/Math.sqrt(denom/n2) : 0;
                const kr = se ? sl/se : 0;
                const sq = sd ? (mn/sd)*Math.sqrt(n) : 0;
                const wp = n ? (wc/n)*100 : 0, lp = n ? (lc/n)*100 : 0;
                return {{ totalPL:tp, avgDailyPL:adp, avgDailyVolume:adv, avgPerShare:aps, avgTrade:mn, totalTrades:n, winCount:wc, winPct:wp, lossCount:lc, lossPct:lp, avgWin:aw, avgLoss:al, stdDev:sd, probRandom:pr, kRatio:kr, sqn:sq }};
            }}

            function erf(x) {{
                const a1=0.254829592,a2=-0.284496736,a3=1.421413741,a4=-1.453152027,a5=1.061405429,p=0.3275911;
                const s = x<0?-1:1; x=Math.abs(x);
                const t = 1/(1+p*x);
                return s * (1 - (((((a5*t+a4)*t+a3)*t+a2)*t+a1)*t*Math.exp(-x*x)));
            }}

            function formatCurrency(val) {{
                return (val<0?'-$':'$') + Math.abs(val).toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
            }}

            function updateBuildCounts() {{
                document.querySelector('#br-count-a strong').textContent = filterTrades('a').length;
                document.querySelector('#br-count-b strong').textContent = filterTrades('b').length;
            }}

            function generateBuildReport() {{
                const ma = computeMetrics(filterTrades('a'));
                const mb = computeMetrics(filterTrades('b'));
                const ct = document.getElementById('br-table-container');
                const rd = document.getElementById('br-results');
                if (!ma && !mb) {{ rd.style.display='block'; ct.innerHTML='<div class=\"br-no-data\">No data found for either group. Adjust your filters.</div>'; return; }}
                rd.style.display='block';
                const rows = [
                    {{label:'Total Gain / Loss',key:'totalPL',fmt:'currency'}},
                    {{label:'Average Daily Gain / Loss',key:'avgDailyPL',fmt:'currency'}},
                    {{label:'Average Daily Volume',key:'avgDailyVolume',fmt:'number'}},
                    {{label:'Average Per-Share Gain / Loss',key:'avgPerShare',fmt:'currency'}},
                    {{label:'Average Trade Gain / Loss',key:'avgTrade',fmt:'currency'}},
                    {{label:'Total Number of Trades',key:'totalTrades',fmt:'integer'}},
                    {{label:'Winning Trades',key:'winCount',fmt:'winloss'}},
                    {{label:'Losing Trades',key:'lossCount',fmt:'winloss'}},
                    {{label:'Average Winning Trade',key:'avgWin',fmt:'currency'}},
                    {{label:'Average Losing Trade',key:'avgLoss',fmt:'currency'}},
                    {{label:'Trade P&L Standard Deviation',key:'stdDev',fmt:'currency'}},
                    {{label:'Probability of Random Chance',key:'probRandom',fmt:'pct'}},
                    {{label:'K-Ratio',key:'kRatio',fmt:'decimal'}},
                    {{label:'SQN',key:'sqn',fmt:'decimal'}}
                ];
                let h = '<table class=\"br-table\"><thead><tr><th style=\"width:35%;\">Metric</th><th class=\"value-a\" style=\"width:32.5%;\">Group A <span class=\"br-badge br-badge-a\">A</span></th><th class=\"value-b\" style=\"width:32.5%;\">Group B <span class=\"br-badge br-badge-b\">B</span></th></tr></thead><tbody>';
                rows.forEach(r => {{
                    const va = ma ? ma[r.key] : null;
                    const vb = mb ? mb[r.key] : null;
                    const f = (v,fmt,m) => {{
                        if (v===null||v===undefined) return '<span class=\"br-no-data\">No data found</span>';
                        if (fmt==='currency') return formatCurrency(v);
                        if (fmt==='number') return v.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
                        if (fmt==='integer') return Math.round(v).toLocaleString();
                        if (fmt==='pct') return v.toFixed(2)+'%';
                        if (fmt==='decimal') return v.toFixed(2);
                        if (fmt==='winloss') return v+' ('+(r.key==='winCount'?(m.winPct||0):(m.lossPct||0)).toFixed(1)+'%)';
                        return v;
                    }};
                    h += '<tr><td class=\"metric-name\">'+r.label+'</td><td class=\"value-a\">'+(ma?f(va,r.fmt,ma):'<span class=\"br-no-data\">No data found</span>')+'</td><td class=\"value-b\">'+(mb?f(vb,r.fmt,mb):'<span class=\"br-no-data\">No data found</span>')+'</td></tr>';
                }});
                h += '</tbody></table>';
                ct.innerHTML = h;
            }}

            function renderBuildReport() {{
                if (!buildReportInitialized) {{
                    buildReportInitialized = true;
                    buildTagOptions('a'); buildTagOptions('b'); updateBuildCounts();
                    document.addEventListener('click', function(e) {{
                        document.querySelectorAll('.br-tag-dropdown').forEach(dd => {{
                            if (!dd.closest('.br-tag-wrap')) dd.classList.remove('show');
                        }});
                    }});
                }}
            }}

            function resetBuildReport() {{
                ['a','b'].forEach(g => {{
                    document.getElementById('br-symbol-'+g).value = '';
                    document.getElementById('br-side-'+g).value = 'all';
                    document.getElementById('br-duration-'+g).value = 'all';
                    document.getElementById('br-pnl-'+g).value = 'all';
                    document.getElementById('br-datefrom-'+g).value = '';
                    document.getElementById('br-dateto-'+g).value = '';
                    brTags[g] = [];
                    buildTagOptions(g); renderTagChips(g);
                }});
                updateBuildCounts();
                document.getElementById('br-results').style.display = 'none';
                document.getElementById('br-table-container').innerHTML = '';
            }}
        // Laser scan bar effect on KPI cards
        document.addEventListener('mouseover', function (e) {{
            var card = e.target.closest('.card, .month-card');
            if (card && !card.querySelector('.chart-container')) {{
                var old = card.querySelector('.laser-bar');
                if (old) return;
                var bar = document.createElement('div');
                bar.className = 'laser-bar';
                card.appendChild(bar);
                setTimeout(function () {{ bar.remove(); }}, 700);
            }}
        }});
    </script>

    <!-- Circuit Board Background JS -->
    <script>
        (function () {{
            const canvas = document.getElementById('circuit-bg');
            const ctx = canvas.getContext('2d');
            let accentRGB = '0, 212, 255';
            const GRID = 30;
            let W, H, cols, rows, nodes, pulses;

            function hexToRgb(hex) {{
                const r = /^#?([a-f\\d]{{2}})([a-f\\d]{{2}})([a-f\\d]{{2}})$/i.exec(hex);
                return r ? `${{parseInt(r[1], 16)}}, ${{parseInt(r[2], 16)}}, ${{parseInt(r[3], 16)}}` : null;
            }}

            function updateAccentColor() {{
                const hex = getComputedStyle(document.documentElement).getPropertyValue('--accent-primary').trim();
                const rgb = hexToRgb(hex);
                if (rgb) accentRGB = rgb;
            }}

            function resize() {{
                W = canvas.width = window.innerWidth;
                H = canvas.height = window.innerHeight;
                cols = Math.ceil(W / GRID) + 1;
                rows = Math.ceil(H / GRID) + 1;
                nodes = []; pulses = [];
                for (let c = 0; c < cols; c++) {{
                    for (let r = 0; r < rows; r++) {{
                        if (Math.random() < 0.18) nodes.push({{ x: c * GRID, y: r * GRID, col: c, row: r }});
                    }}
                }}
                const edges = [];
                for (let i = 0; i < nodes.length; i++) {{
                    for (let j = i + 1; j < nodes.length; j++) {{
                        const a = nodes[i], b = nodes[j];
                        const dx = Math.abs(a.col - b.col), dy = Math.abs(a.row - b.row);
                        if (((dx === 0 && dy <= 4) || (dy === 0 && dx <= 4)) && Math.random() < 0.55) {{
                            const mid = {{ x: b.x, y: a.y }};
                            edges.push({{ a, b, segments: [{{x1:a.x,y1:a.y,x2:mid.x,y2:mid.y}}, {{x1:mid.x,y1:mid.y,x2:b.x,y2:b.y}}] }});
                        }}
                    }}
                }}
                for (let i = 0; i < 12; i++) {{ const e = edges[Math.floor(Math.random() * edges.length)]; if (e) spawnPulse(e); }}
                canvas._edges = edges;
            }}

            function spawnPulse(edge) {{
                const tl = Math.abs(edge.segments[0].x2-edge.segments[0].x1)+Math.abs(edge.segments[0].y2-edge.segments[0].y1)+Math.abs(edge.segments[1].x2-edge.segments[1].x1)+Math.abs(edge.segments[1].y2-edge.segments[1].y1);
                pulses.push({{ edge, t: 0, speed: 0.3 + Math.random() * 0.5, totalLen: tl, alpha: 0.6 + Math.random() * 0.4 }});
            }}

            function draw() {{
                updateAccentColor();
                const CC = `rgba(${{accentRGB}},`;
                ctx.clearRect(0, 0, W, H);
                const edges = canvas._edges || [];
                ctx.lineWidth = 1;
                for (const e of edges) {{
                    ctx.strokeStyle = CC + '0.07)'; ctx.beginPath();
                    for (const s of e.segments) {{ ctx.moveTo(s.x1, s.y1); ctx.lineTo(s.x2, s.y2); }}
                    ctx.stroke();
                }}
                for (const n of nodes) {{ ctx.beginPath(); ctx.arc(n.x, n.y, 1.5, 0, Math.PI * 2); ctx.fillStyle = CC + '0.18)'; ctx.fill(); }}
                const alive = [];
                for (const p of pulses) {{
                    p.t += p.speed;
                    if (p.t <= p.totalLen) {{
                        const hd = (ps) => {{ const d=p.t; const l0=Math.abs(ps[0].x2-ps[0].x1)+Math.abs(ps[0].y2-ps[0].y1); if(d<=l0){{const f=d/Math.max(l0,.001);return{{x:ps[0].x1+(ps[0].x2-ps[0].x1)*f,y:ps[0].y1+(ps[0].y2-ps[0].y1)*f}};}}else{{const f=(d-l0)/Math.max(Math.abs(ps[1].x2-ps[1].x1)+Math.abs(ps[1].y2-ps[1].y1),.001);return{{x:ps[1].x1+(ps[1].x2-ps[1].x1)*Math.min(f,1),y:ps[1].y1+(ps[1].y2-ps[1].y1)*Math.min(f,1)}};}}}};
                        const h = hd(p.edge.segments);
                        ctx.beginPath(); ctx.arc(h.x, h.y, 2.5, 0, Math.PI * 2);
                        ctx.fillStyle = CC + p.alpha.toFixed(2) + ')';
                        ctx.shadowBlur = 8; ctx.shadowColor = CC + '1)'; ctx.fill(); ctx.shadowBlur = 0;
                        alive.push(p);
                    }}
                }}
                pulses = alive;
                if (pulses.length < 8 && edges.length > 0) {{ const e = edges[Math.floor(Math.random() * edges.length)]; if (e) spawnPulse(e); }}
                requestAnimationFrame(draw);
            }}
            window.addEventListener('resize', resize);
            resize();
            draw();
        }})();
    </script>
</body>
</html>
"""
    return html

def main():
    # Helper to deduplicate items choosing the maximum count found in any single file
    def merge_item_counts(dir_path, process_func):
        global_max_counts = collections.defaultdict(int)
        if not os.path.exists(dir_path):
            return []
        
        print(f"Scanning directory: {dir_path}...")
        for filename in os.listdir(dir_path):
            if filename.lower().endswith('.csv'):
                filepath = os.path.join(dir_path, filename)
                print(f"  Reading: {filename}...")
                items = process_func(filepath)
                
                # Count frequencies in CURRENT file
                file_counts = collections.Counter(items)
                
                # Update global record with the MAX frequency ever seen for each item
                for item, count in file_counts.items():
                    if count > global_max_counts[item]:
                        global_max_counts[item] = count
        
        # Flatten back to a list
        final_list = []
        for item, count in global_max_counts.items():
            final_list.extend([item] * count)
        return final_list

    # 1. Process Schwab executions
    print("Processing Schwab executions...")
    all_executions = merge_item_counts(SCHWAB_DIR, process_execution_trades)
    print(f"Total deduplicated executions: {len(all_executions)}")
    
    print("Matching execution trades...")
    closed_execution_trades = match_trades(all_executions)
    print(f"Generated {len(closed_execution_trades)} closed trades from executions.")

    # 2. Process Alaric reports (from PropReports)
    print("Processing Alaric reports...")
    all_alaric_trades = merge_item_counts(ALARIC_DIR, process_alaric_trades)
    print(f"Total deduplicated Alaric trades: {len(all_alaric_trades)}")

    # 3. Process MetaTrader trades (pre-matched)
    print("Processing MetaTrader trades...")
    all_mt_trades = merge_item_counts(METATRADER_DIR, process_metatrader_trades)
    print(f"Total deduplicated MetaTrader trades: {len(all_mt_trades)}")

    # 4. Process DAS Trader executions
    print("Processing DAS executions...")
    all_das_executions = merge_item_counts(DAS_DIR, process_das_trades)
    print(f"Total deduplicated DAS executions: {len(all_das_executions)}")
    closed_das_trades = match_trades(all_das_executions)
    print(f"Generated {len(closed_das_trades)} closed trades from DAS.")

    # 5. Process ThinkOrSwim executions
    print("Processing ThinkOrSwim executions...")
    all_tos_executions = merge_item_counts(TOS_DIR, process_tos_trades)
    print(f"Total deduplicated TOS executions: {len(all_tos_executions)}")
    closed_tos_trades = match_trades(all_tos_executions)
    print(f"Generated {len(closed_tos_trades)} closed trades from TOS.")

    # 6. Process Generic CSV imports
    print("Processing Generic trade imports...")
    all_generic_items = merge_item_counts(GENERIC_DIR, process_generic_trades)
    # Generic can return Trade or ClosedTrade — separate them
    generic_executions = [x for x in all_generic_items if isinstance(x, Trade)]
    generic_closed = [x for x in all_generic_items if isinstance(x, ClosedTrade)]
    closed_generic_trades = match_trades(generic_executions) + generic_closed
    print(f"Total deduplicated Generic items: {len(all_generic_items)} -> "
          f"{len(closed_generic_trades)} closed trades.")

    # Combine all trades
    all_closed_trades = (closed_execution_trades + all_alaric_trades + all_mt_trades +
                         closed_das_trades + closed_tos_trades + closed_generic_trades)
    print(f"Total overall closed trades: {len(all_closed_trades)}")

    # Apply saved tags from tags.json
    saved_tags = load_tags()
    if saved_tags:
        applied = 0
        for t in all_closed_trades:
            tid = t.trade_id
            if tid in saved_tags:
                tag_data = saved_tags[tid]
                if isinstance(tag_data, str):
                    # Legacy format: just a string tag
                    t.entry_tag = tag_data
                else:
                    t.entry_tag = tag_data.get('entry_tag', '')
                    t.exit_tag = tag_data.get('exit_tag', '')
                    t.note = tag_data.get('note', '')
                applied += 1
        print(f"Applied saved tags to {applied} trades.")
    
    # 3. Process Expenses (Gastos)
    print("Processing Expenses...")
    all_expense_items = merge_item_counts(GASTOS_DIR, process_gastos)
    
    # Aggregated back to date -> total
    expenses_data = collections.defaultdict(float)
    for date_key, category, comment, amount in all_expense_items:
        expenses_data[date_key] += amount
    print(f"Total expense days after deduplication: {len(expenses_data)}.")

    print("Generating report...")
    html_content = generate_html_report(all_closed_trades, expenses_data)
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Success! Report saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error writing HTML: {e}")

if __name__ == "__main__":
    main()

