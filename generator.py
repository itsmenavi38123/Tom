import os
import random
import uuid
import shutil
import pandas as pd
from datetime import datetime, timedelta
from zipfile import ZipFile
from typing import Dict, List, Optional
import logging
from calendar import monthrange
from collections import defaultdict

logger = logging.getLogger(__name__)

class DatasetGenerator:
    def __init__(self, config: Dict):
        self.config = config
        self.set_random_seed()
        self.faker = self.setup_faker()
        self.generated_customers = []
        self.generated_vendors = []
        self.generated_products = []
        self.generated_invoices = pd.DataFrame()
        self.start_date = self._parse_start_date(self.config.get('start_date'))
        self.industry_profile = self._build_industry_profile()
        self.expense_occurrences: List[Dict] = []
        self.personal_expenses: List[Dict] = []
        self.sales_deposits: List[Dict] = []
        self.invoice_payments: List[Dict] = []
        self.refunds: List[Dict] = []
        self.savings_transfers: List[Dict] = []
        self.misc_bank_withdrawals: List[Dict] = []
        self.credit_card_plan = {'transactions': pd.DataFrame(), 'payments': []}
        # Track intentional changes for answer_key
        self.answer_key: List[str] = []
        # Messiness level: 'none', 'low', 'medium', 'high' -> percent of rows to alter
        level = str(self.config.get('messiness', 'none')).lower()
        self.messiness_map = {'none': 0, 'low': 5, 'medium': 10, 'high': 15}
        self.messiness_pct = self.messiness_map.get(level, 0)
        
        raw_error_counts = self.config.get('error_counts', {}) or {}
        self.error_counts = {}
        for key, value in raw_error_counts.items():
            try:
                self.error_counts[key] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        self.invoice_new_customers = max(0, int(self.config.get('invoice_new_customers', 0)))
        self._invoice_new_customers_remaining = self.invoice_new_customers
        self.use_account_numbers = bool(self.config.get('use_account_numbers', True))
        self.us_states = [
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
            'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM',
            'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA',
            'WV', 'WI', 'WY'
        ]
        self.used_product_names = set()
        self.client_code = self._derive_client_code(self.config.get('client_name', 'Client'))
        # Merchant & description libraries for more realistic transactions
        self.extra_vendor_names = [
            'SRP', 'APS', 'Salt River Project', 'Cox Communications', 'CenturyLink',
            'Verizon Wireless', 'AT&T Mobility', 'Waste Management', 'Delta Air Lines',
            'Southwest Airlines', 'Staples Advantage', 'Office Depot', 'Amazon Business',
            'American Express', 'Costco Wholesale', 'Shell Oil', 'Circle K', 'QuickTrip',
            'Stripe', 'Square', 'PayPal', 'Intuit Payroll'
        ]
        self.location_suffixes = [
            'PHOENIX AZ', 'AUSTIN TX', 'SAN DIEGO CA', 'SCOTTSDALE AZ', 'DALLAS TX',
            'SAN FRANCISCO CA', 'CHANDLER AZ', 'MESA AZ', 'SEATTLE WA', 'DENVER CO'
        ]
        self.credit_card_payment_labels = [
            'Business Visa', 'Corporate Mastercard', 'Amex Platinum', 'Capital One Spark'
        ]
        
    def set_random_seed(self):
        seed = self.config.get('random_seed', -1)
        if seed == -1:
            seed = random.randint(1, 999999)
        random.seed(seed)
        logger.info(f"Using random seed: {seed}")
        
    def setup_faker(self):
        try:
            from faker import Faker
            # Force US-only addresses
            fake = Faker('en_US')
            return fake
        except Exception:
            # Minimal fallback fake generator to avoid hard dependency failures during tests
            class SimpleFake:
                def city(self):
                    return random.choice(['Phoenix', 'Tempe', 'Scottsdale', 'Chandler', 'Mesa'])
                def zipcode(self):
                    return f"{random.randint(85000, 99999)}"
                def street_address(self):
                    return f"{random.randint(100,9999)} {random.choice(['Main St', 'Baseline Rd', 'Oak Ave', '1st St'])}"
                def company(self):
                    return random.choice(['Sunrise Wellness LLC','Desert Yoga Studio','Cactus Health Clinic','Oasis Therapy Center'])
                def first_name(self):
                    return random.choice(['Alex','Sam','Taylor','Jordan','Casey'])
                def last_name(self):
                    return random.choice(['Smith','Johnson','Lee','Brown','Garcia'])
                def email(self):
                    return f"{self.first_name().lower()}@example.com"
                def phone_number(self):
                    return f"{random.randint(200,999)}{random.randint(200,999)}{random.randint(1000,9999)}"
                def company_email(self):
                    return f"contact@{self.company().replace(' ', '').lower()}.com"
                def sentence(self, nb_words=6):
                    words = [random.choice(['quality','service','monthly','subscription','package','session','rate','product']) for _ in range(nb_words)]
                    return ' '.join(words)
            return SimpleFake()
    
    def slugify(self, s: str) -> str:
        """Convert string to filesystem-safe name"""
        valid_chars = "abcdefghijklmnopqrstuvwxyz0123456789_-"
        s = s.lower().replace(' ', '_')
        return ''.join(ch for ch in s if ch in valid_chars)
    
    def ensure_dir(self, path: str):
        os.makedirs(path, exist_ok=True)
    
    def _derive_client_code(self, name: str) -> str:
        parts = [p for p in ''.join(ch if ch.isalnum() or ch == ' ' else ' ' for ch in name).split() if p]
        if not parts:
            return 'CLIENT'
        code = ''.join(part[0].upper() for part in parts[:3])
        return code or 'CLIENT'

    def _parse_start_date(self, value: Optional[str]) -> datetime:
        if not value:
            today = datetime.today()
            return datetime(today.year, today.month, 1)
        for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
            try:
                parsed = datetime.strptime(value, fmt)
                return datetime(parsed.year, parsed.month, parsed.day)
            except ValueError:
                continue
        today = datetime.today()
        return datetime(today.year, today.month, 1)

    def _month_start(self, offset: int) -> datetime:
        base = self.start_date
        year = base.year + (base.month - 1 + offset) // 12
        month = (base.month - 1 + offset) % 12 + 1
        return datetime(year, month, 1)

    def _days_in_month(self, ref_date: datetime) -> int:
        return monthrange(ref_date.year, ref_date.month)[1]

    def _build_industry_profile(self) -> Dict:
        shared_vendors = [
            'Cox Communications', 'SRP', 'Waste Management', 'Office Depot',
            'Staples', 'Amazon Business', 'FedEx', 'UPS', 'Gusto Payroll',
            'QuickBooks Payroll', 'State Farm Insurance', 'Google Workspace',
            'Microsoft 365', 'Adobe Creative Cloud', 'Meta Ads'
        ]
        base_expenses = [
            {'name': 'Rent', 'vendor': 'Main Street Properties', 'amount_range': (2800, 4800), 'frequency': 'monthly', 'day': 1, 'method': 'ach', 'description': 'Office lease payment'},
            {'name': 'Payroll', 'vendor': 'Gusto Payroll', 'amount_range': (9000, 15000), 'frequency': 'biweekly', 'day': 5, 'method': 'ach', 'description': 'Payroll funding'},
            {'name': 'Utilities', 'vendor': 'SRP', 'amount_range': (320, 580), 'frequency': 'monthly', 'day': 7, 'method': 'ach', 'description': 'Electric and utilities'},
            {'name': 'Internet', 'vendor': 'Cox Communications', 'amount_range': (160, 260), 'frequency': 'monthly', 'day': 9, 'method': 'ach', 'description': 'Internet service'},
            {'name': 'Software', 'vendor': 'Google Workspace', 'amount_range': (120, 200), 'frequency': 'monthly', 'day': 12, 'method': 'credit_card', 'description': 'Software subscription'},
            {'name': 'Insurance', 'vendor': 'State Farm Insurance', 'amount_range': (380, 720), 'frequency': 'monthly', 'day': 18, 'method': 'ach', 'description': 'Business insurance'},
            {'name': 'Supplies', 'vendor': 'Office Depot', 'amount_range': (180, 520), 'frequency': 'monthly', 'day': 20, 'method': 'credit_card', 'description': 'Office and breakroom supplies'},
            {'name': 'Marketing', 'vendor': 'Meta Ads', 'amount_range': (700, 1900), 'frequency': 'monthly', 'day': 23, 'method': 'credit_card', 'description': 'Digital advertising'},
            {'name': 'Shipping', 'vendor': 'UPS', 'amount_range': (140, 420), 'frequency': 'weekly', 'method': 'credit_card', 'description': 'Outbound shipments'},
            {'name': 'Cleaning', 'vendor': 'Waste Management', 'amount_range': (140, 280), 'frequency': 'monthly', 'day': 15, 'method': 'ach', 'description': 'Waste services'}
        ]
        base_profile = {
            'monthly_sales_range': (35000, 65000),
            'sale_amount_range': (35, 320),
            'payouts_per_month_range': (10, 16),
            'sales_processors': [
                {'name': 'Stripe', 'label': 'Stripe Payout', 'type': 'processor', 'fee_range': (0.024, 0.032)},
                {'name': 'Square', 'label': 'Square Settlement', 'type': 'processor', 'fee_range': (0.025, 0.035)},
                {'name': 'Shopify', 'label': 'Shopify Payout', 'type': 'processor', 'fee_range': (0.024, 0.030)},
                {'name': 'Cash', 'label': 'Cash Deposit', 'type': 'cash', 'fee_range': (0.0, 0.0)},
                {'name': 'ACH', 'label': 'ACH Payment', 'type': 'ach', 'fee_range': (0.0, 0.0)}
            ],
            'vendors': shared_vendors,
            'personal_vendors': ['Starbucks', "McDonald's", 'Chipotle', 'Petsmart', 'Petco', 'Target', 'Walmart', 'Costco'],
            'expense_templates': base_expenses,
            'starting_balance_range': (25000, 60000),
            'min_balance': 5000,
            'max_balance': 90000,
            'refunds_per_month': (1, 3)
        }
        restaurant_expenses = [
            {'name': 'Food Inventory - Sysco', 'vendor': 'Sysco', 'amount_range': (2800, 5600), 'frequency': 'weekly', 'method': 'ach', 'description': 'Food inventory delivery'},
            {'name': 'Food Inventory - US Foods', 'vendor': 'US Foods', 'amount_range': (2600, 5200), 'frequency': 'weekly', 'method': 'ach', 'description': 'Kitchen supply order'},
            {'name': 'Beverage Delivery', 'vendor': 'Coca-Cola Bottling', 'amount_range': (650, 1400), 'frequency': 'monthly', 'day': 6, 'method': 'ach', 'description': 'Beverage restock'},
            {'name': 'Payroll', 'vendor': 'Gusto Payroll', 'amount_range': (11000, 19000), 'frequency': 'biweekly', 'day': 5, 'method': 'ach', 'description': 'Restaurant payroll'},
            {'name': 'Rent', 'vendor': 'Main Street Properties', 'amount_range': (4800, 8200), 'frequency': 'monthly', 'day': 1, 'method': 'ach', 'description': 'Restaurant lease'},
            {'name': 'Grease & Cleaning', 'vendor': 'Ecolab', 'amount_range': (320, 640), 'frequency': 'monthly', 'day': 10, 'method': 'ach', 'description': 'Cleaning and sanitation'},
            {'name': 'Delivery Fees', 'vendor': 'DoorDash', 'amount_range': (850, 1900), 'frequency': 'monthly', 'day': 20, 'method': 'credit_card', 'description': 'Delivery platform fees'},
            {'name': 'POS Software', 'vendor': 'Toast POS', 'amount_range': (320, 520), 'frequency': 'monthly', 'day': 12, 'method': 'credit_card', 'description': 'POS subscription'}
        ]
        retail_expenses = base_expenses[:-2] + [
            {'name': 'Wholesale Inventory', 'vendor': 'Amazon Vendor Services', 'amount_range': (4200, 9600), 'frequency': 'monthly', 'day': 4, 'method': 'ach', 'description': 'Inventory buy'},
            {'name': 'Shopify Apps', 'vendor': 'Shopify', 'amount_range': (180, 420), 'frequency': 'monthly', 'day': 14, 'method': 'credit_card', 'description': 'App marketplace fees'},
            {'name': 'Fulfillment Fees', 'vendor': 'ShipStation', 'amount_range': (220, 480), 'frequency': 'monthly', 'day': 16, 'method': 'credit_card', 'description': 'Fulfillment platform'},
            {'name': 'Advertising', 'vendor': 'Google Ads', 'amount_range': (900, 2500), 'frequency': 'monthly', 'day': 25, 'method': 'credit_card', 'description': 'Online advertising'},
            {'name': 'Packaging Supplies', 'vendor': 'Uline', 'amount_range': (280, 640), 'frequency': 'monthly', 'day': 18, 'method': 'credit_card', 'description': 'Packaging materials'}
        ]
        ecommerce_expenses = [
            {'name': 'SaaS Platform', 'vendor': 'Shopify', 'amount_range': (260, 480), 'frequency': 'monthly', 'day': 3, 'method': 'credit_card', 'description': 'Platform subscription'},
            {'name': 'Cloud Hosting', 'vendor': 'AWS', 'amount_range': (420, 980), 'frequency': 'monthly', 'day': 11, 'method': 'credit_card', 'description': 'Cloud services'},
            {'name': 'Digital Ads', 'vendor': 'Google Ads', 'amount_range': (1200, 3200), 'frequency': 'monthly', 'day': 20, 'method': 'credit_card', 'description': 'Digital marketing'},
            {'name': 'Email Platform', 'vendor': 'Klaviyo', 'amount_range': (180, 420), 'frequency': 'monthly', 'day': 9, 'method': 'credit_card', 'description': 'Email marketing'},
            {'name': 'Contractor Payment', 'vendor': 'Upwork', 'amount_range': (600, 1600), 'frequency': 'monthly', 'day': 24, 'method': 'ach', 'description': 'Freelance support'},
            {'name': 'Payment Gateway', 'vendor': 'Stripe', 'amount_range': (320, 620), 'frequency': 'monthly', 'day': 16, 'method': 'ach', 'description': 'Gateway fees'}
        ]
        services_expenses = [
            {'name': 'Office Rent', 'vendor': 'Main Street Properties', 'amount_range': (3200, 5200), 'frequency': 'monthly', 'day': 1, 'method': 'ach', 'description': 'Suite lease'},
            {'name': 'Payroll', 'vendor': 'QuickBooks Payroll', 'amount_range': (8000, 15000), 'frequency': 'biweekly', 'day': 6, 'method': 'ach', 'description': 'Staff payroll'},
            {'name': 'Professional Insurance', 'vendor': 'Hiscox Insurance', 'amount_range': (420, 780), 'frequency': 'monthly', 'day': 10, 'method': 'ach', 'description': 'E&O insurance'},
            {'name': 'Software Stack', 'vendor': 'Microsoft 365', 'amount_range': (260, 420), 'frequency': 'monthly', 'day': 12, 'method': 'credit_card', 'description': 'Productivity software'},
            {'name': 'Project Tools', 'vendor': 'Asana', 'amount_range': (180, 260), 'frequency': 'monthly', 'day': 14, 'method': 'credit_card', 'description': 'Project management'},
            {'name': 'Coworking', 'vendor': 'WeWork', 'amount_range': (450, 900), 'frequency': 'monthly', 'day': 5, 'method': 'ach', 'description': 'Flex desks'}
        ]
        wellness_expenses = [
            {'name': 'Studio Rent', 'vendor': 'Oasis Plaza LLC', 'amount_range': (2800, 4200), 'frequency': 'monthly', 'day': 1, 'method': 'ach', 'description': 'Studio lease'},
            {'name': 'Instructor Payroll', 'vendor': 'Gusto Payroll', 'amount_range': (4800, 8200), 'frequency': 'biweekly', 'day': 4, 'method': 'ach', 'description': 'Instructor pay'},
            {'name': 'Retail Inventory', 'vendor': 'Lululemon', 'amount_range': (650, 1400), 'frequency': 'monthly', 'day': 11, 'method': 'credit_card', 'description': 'Boutique restock'},
            {'name': 'Wellness Supplies', 'vendor': 'Yoga Outlet', 'amount_range': (280, 620), 'frequency': 'monthly', 'day': 17, 'method': 'credit_card', 'description': 'Retail items'},
            {'name': 'Booking Software', 'vendor': 'Mindbody', 'amount_range': (240, 420), 'frequency': 'monthly', 'day': 6, 'method': 'credit_card', 'description': 'Scheduling platform'},
            {'name': 'Cleaning Service', 'vendor': 'Ecolab', 'amount_range': (220, 420), 'frequency': 'monthly', 'day': 9, 'method': 'ach', 'description': 'Studio cleaning'},
            {'name': 'Marketing', 'vendor': 'Mailchimp', 'amount_range': (160, 320), 'frequency': 'monthly', 'day': 21, 'method': 'credit_card', 'description': 'Email marketing'}
        ]
        profiles = {
            'restaurant': {
                'monthly_sales_range': (90000, 185000),
                'sale_amount_range': (10, 45),
                'payouts_per_month_range': (22, 34),
                'vendors': ['Sysco', 'US Foods', 'Restaurant Depot', 'Ecolab', 'Gordon Food Service', 'Pepsi Beverage', 'Coca-Cola Bottling', 'Frito-Lay', 'Toast POS', 'DoorDash', 'Uber Eats', 'Grubhub', 'OpenTable', 'Restaurant Solutions Inc'],
                'personal_vendors': ['Costco', "In-N-Out", 'Chick-Fil-A', 'Sam\'s Club', 'Walmart', 'Total Wine'],
                'expense_templates': restaurant_expenses,
                'starting_balance_range': (40000, 95000),
                'min_balance': 8000,
                'max_balance': 140000
            },
            'retail': {
                'monthly_sales_range': (60000, 140000),
                'sale_amount_range': (18, 220),
                'payouts_per_month_range': (14, 22),
                'vendors': ['Amazon Vendor Services', 'Shopify', 'UPS', 'FedEx', 'DHL', 'Canva Pro', 'Adobe', 'Google Ads', 'ShipStation', 'Klaviyo', 'Target', 'Best Buy', 'Uline', 'Square'],
                'personal_vendors': ['Target', 'Best Buy', 'Costco', 'Apple Store', 'REI'],
                'expense_templates': retail_expenses
            },
            'ecommerce': {
                'monthly_sales_range': (45000, 120000),
                'sale_amount_range': (15, 180),
                'payouts_per_month_range': (12, 20),
                'vendors': ['Shopify', 'AWS', 'Stripe', 'Google Ads', 'Facebook Ads', 'Klaviyo', 'ShipBob', 'ShipStation', 'Canva Pro', 'Figma', 'Upwork'],
                'personal_vendors': ['Apple Store', 'B&H Photo', 'Best Buy', 'Walmart', 'DoorDash'],
                'expense_templates': ecommerce_expenses
            },
            'services': {
                'monthly_sales_range': (30000, 90000),
                'sale_amount_range': (150, 850),
                'payouts_per_month_range': (8, 14),
                'vendors': ['WeWork', 'QuickBooks Payroll', 'Hiscox Insurance', 'Microsoft 365', 'Zoom Video', 'Asana', 'Slack Technologies', 'Amazon Business', 'Delta Air Lines', 'Southwest Airlines'],
                'personal_vendors': ['Starbucks', 'Delta Air Lines', 'Lyft', 'Uber', 'Whole Foods'],
                'expense_templates': services_expenses
            },
            'wellness': {
                'monthly_sales_range': (28000, 70000),
                'sale_amount_range': (18, 120),
                'payouts_per_month_range': (12, 18),
                'vendors': ['Mindbody', 'Square', 'Whole Foods', 'Sprouts Market', 'Lululemon', 'Yoga Outlet', 'BlendJet', 'Gusto Payroll', 'QuickBooks Payroll', 'Constant Contact', 'Mailchimp', 'Canva Pro'],
                'personal_vendors': ['Whole Foods', 'Sprouts', 'Trader Joe\'s', 'Target', 'Athleta'],
                'expense_templates': wellness_expenses
            }
        }
        industry_key = str(self.config.get('industry', 'services') or 'services').lower()
        selected = base_profile.copy()
        if industry_key in profiles:
            overrides = profiles[industry_key]
            for key, value in overrides.items():
                selected[key] = value
        return selected

    def _random_business_day(self, month_start: datetime, days_in_month: int, prefer_day: Optional[int] = None) -> datetime:
        if prefer_day:
            day = max(1, min(days_in_month, prefer_day + random.randint(-2, 2)))
        else:
            day = random.randint(1, days_in_month)
        candidate = month_start + timedelta(days=day - 1)
        # Adjust weekends back to Friday
        if candidate.weekday() == 5:  # Saturday
            candidate -= timedelta(days=1)
        elif candidate.weekday() == 6:  # Sunday
            candidate -= timedelta(days=2)
        return candidate

    def _random_amount(self, amount_range: tuple) -> float:
        low, high = amount_range
        return round(random.uniform(low, high), 2)

    def _expand_expense_templates(self) -> List[Dict]:
        occurrences: List[Dict] = []
        months = self.config['months']
        templates = self.industry_profile['expense_templates']
        for month in range(months):
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            for tpl in templates:
                freq = tpl.get('frequency', 'monthly')
                base_day = tpl.get('day', 5)
                schedule_days: List[int] = []
                if freq == 'weekly':
                    day_cursor = base_day
                    while day_cursor <= dim:
                        schedule_days.append(day_cursor)
                        day_cursor += 7
                elif freq == 'biweekly':
                    schedule_days = [base_day, base_day + 14]
                else:  # monthly/default
                    schedule_days = [base_day]
                for day in schedule_days:
                    if day > dim:
                        continue
                    occ_date = self._random_business_day(month_start, dim, day)
                    amount = self._random_amount(tpl['amount_range'])
                    occurrences.append({
                        'month': month,
                        'date': occ_date,
                        'vendor': tpl['vendor'],
                        'amount': amount,
                        'method': tpl.get('method', 'ach'),
                        'description': tpl.get('description', tpl['name']),
                        'category': tpl['name'],
                        'source': 'template'
                    })
            # add a few misc recurring expenses each month
            misc_count = random.randint(2, 4)
            for _ in range(misc_count):
                vendor = random.choice(self.industry_profile['vendors'])
                method = random.choice(['ach', 'credit_card'])
                amount = round(random.uniform(90, 650), 2)
                occ_date = self._random_business_day(month_start, dim)
                occurrences.append({
                    'month': month,
                    'date': occ_date,
                    'vendor': vendor,
                    'amount': amount,
                    'method': method,
                    'description': f"{vendor} subscription",
                    'category': 'Operating Expense',
                    'source': 'supplemental'
                })
        return occurrences

    def _plan_misc_personal_purchases(self) -> List[Dict]:
        entries: List[Dict] = []
        months = self.config['months']
        personal_vendors = self.industry_profile['personal_vendors']
        for month in range(months):
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            count = random.randint(1, 3)
            for _ in range(count):
                vendor = random.choice(personal_vendors)
                method = 'credit_card' if random.random() > 0.3 else 'bank'
                amount = round(random.uniform(18, 220), 2)
                occ_date = self._random_business_day(month_start, dim)
                entries.append({
                    'month': month,
                    'date': occ_date,
                    'vendor': vendor,
                    'amount': amount,
                    'method': method,
                    'description': f"{vendor} Personal Purchase",
                    'category': 'Personal',
                    'source': 'personal'
                })
        return entries

    def _simulate_sales_activity(self) -> None:
        months = self.config['months']
        customer_names = []
        if isinstance(self.generated_customers, pd.DataFrame) and not self.generated_customers.empty:
            customer_names = self.generated_customers['Display Name'].tolist()
        if not customer_names:
            customer_names = ['Client Customer']
        deposits: List[Dict] = []
        refunds: List[Dict] = []
        profile = self.industry_profile
        for month in range(months):
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            target_sales = random.uniform(*profile['monthly_sales_range'])
            payout_count = random.randint(*profile['payouts_per_month_range'])
            if payout_count <= 0:
                payout_count = 1
            raw_payouts = []
            for _ in range(payout_count):
                processor = random.choice(profile['sales_processors'])
                sale_batches = random.randint(6, 30)
                gross = sum(random.uniform(*profile['sale_amount_range']) for _ in range(sale_batches))
                raw_payouts.append({'processor': processor, 'gross': gross})
            total_gross = sum(item['gross'] for item in raw_payouts)
            scale = target_sales / total_gross if total_gross else 1
            for payout in raw_payouts:
                gross = payout['gross'] * scale
                processor = payout['processor']
                fee_pct = random.uniform(*processor['fee_range'])
                fee_amount = gross * fee_pct
                net_amount = round(gross - fee_amount, 2)
                if processor['type'] == 'processor':
                    descriptor = f"{processor['label']} {random.randint(100000, 999999)}"
                elif processor['type'] == 'cash':
                    descriptor = "Cash Deposit - Front Counter"
                else:
                    descriptor = f"{processor['label']} - {random.choice(customer_names)}"
                deposit_date = self._random_business_day(month_start, dim)
                deposits.append({
                    'month': month,
                    'date': deposit_date,
                    'amount': net_amount,
                    'description': descriptor,
                    'source': processor['name'],
                    'fee_amount': round(fee_amount, 2)
                })
            refund_min, refund_max = profile['refunds_per_month']
            refund_target = random.randint(refund_min, refund_max)
            month_deposits = [d for d in deposits if d['month'] == month]
            refund_candidates = month_deposits or deposits
            for _ in range(refund_target):
                if not refund_candidates:
                    break
                base = random.choice(refund_candidates)
                amount = base['amount']
                refund_amount = round(amount * random.uniform(0.5, 1.0), 2)
                refund_date = self._random_business_day(month_start, dim)
                customer = random.choice(customer_names)
                refunds.append({
                    'month': month,
                    'date': refund_date,
                    'amount': -refund_amount,
                    'description': f"Refund - {customer}"
                })
        self.sales_deposits = deposits
        self.refunds = refunds

    def _plan_invoice_payments(self) -> List[Dict]:
        invoices = self.generated_invoices
        if invoices.empty:
            return []
        invoices = invoices.copy()
        paid_pct = max(0, min(100, int(self.config.get('invoice_pct_paid', 80))))
        paid_count = max(0, round(len(invoices) * paid_pct / 100))
        if paid_count == 0:
            return []
        paid_indices = random.sample(list(invoices.index), k=paid_count)
        payments: List[Dict] = []
        for idx in paid_indices:
            invoice_row = invoices.loc[idx]
            invoice_date = datetime.strptime(invoice_row['Invoice Date'], '%m/%d/%Y')
            payment_lag = random.randint(3, max(6, self.config.get('invoice_due_days', 15)))
            payment_date = invoice_date + timedelta(days=payment_lag)
            last_month = self._month_start(self.config['months'] - 1)
            last_day = self._days_in_month(last_month)
            window_end = last_month + timedelta(days=last_day - 1)
            if payment_date > window_end:
                payment_date = window_end - timedelta(days=random.randint(0, 3))
            method = random.choice(['ach', 'credit_card', 'cash'])
            amount = float(invoice_row['Amount'])
            net_amount = amount
            fee = 0.0
            if method == 'credit_card':
                fee = amount * random.uniform(0.023, 0.05)
                net_amount = amount - fee
            description = f"Invoice Payment - {invoice_row['Customer']}"
            payments.append({
                'month': max(0, (payment_date.year - self.start_date.year) * 12 + (payment_date.month - self.start_date.month)),
                'date': payment_date,
                'amount': round(net_amount, 2),
                'description': description,
                'customer': invoice_row['Customer'],
                'method': method,
                'fee_amount': round(fee, 2)
            })
        payments.sort(key=lambda x: x['date'])
        return payments

    def _schedule_savings_transfers(self) -> List[Dict]:
        if not self.config.get('include_savings_account'):
            return []
        transfers: List[Dict] = []
        per_month = max(0, int(self.config.get('savings_transfer_per_month', 0)))
        if per_month == 0:
            per_month = 1
        for month in range(self.config['months']):
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            for _ in range(per_month):
                amount = round(random.uniform(400, 2500), 2)
                date = self._random_business_day(month_start, dim)
                direction = 'to_savings' if random.random() > 0.2 else 'from_savings'
                transfers.append({
                    'month': month,
                    'date': date,
                    'amount': amount,
                    'direction': direction,
                    'description': f"Transfer {'to' if direction == 'to_savings' else 'from'} Savings"
                })
        transfers.sort(key=lambda x: x['date'])
        return transfers

    def _plan_misc_bank_withdrawals(self) -> List[Dict]:
        months = self.config['months']
        entries: List[Dict] = []
        for month in range(months):
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            count = random.randint(1, 3)
            for _ in range(count):
                amount = round(random.uniform(120, 480), 2)
                date = self._random_business_day(month_start, dim)
                entries.append({
                    'month': month,
                    'date': date,
                    'amount': -amount,
                    'description': f"Cash Withdrawal {random.randint(1000,9999)}"
                })
        return entries

    def plan_credit_card_activity(self) -> Dict:
        months = self.config['months']
        charges_by_month: Dict[int, List[Dict]] = defaultdict(list)
        for entry in self.expense_occurrences + self.personal_expenses:
            if entry['method'] == 'credit_card':
                charges_by_month[entry['month']].append(entry)
        target_per_month = max(4, int(self.config.get('cc_txn_per_month', 40) / months))
        for month in range(months):
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            current = len(charges_by_month[month])
            filler_needed = max(0, target_per_month - current)
            for _ in range(filler_needed):
                vendor = random.choice(self.industry_profile['vendors'])
                amount = round(random.uniform(40, 420), 2)
                date = self._random_business_day(month_start, dim)
                charges_by_month[month].append({
                    'month': month,
                    'date': date,
                    'vendor': vendor,
                    'amount': amount,
                    'method': 'credit_card',
                    'description': f"{vendor} POS {self._random_location_suffix()}",
                    'category': 'Operations',
                    'source': 'filler'
                })
        card_rows: List[Dict] = []
        payments: List[Dict] = []
        for month, entries in charges_by_month.items():
            month_total = 0.0
            for entry in entries:
                amount = round(-abs(entry['amount']), 2)
                card_rows.append({
                    'Date': entry['date'].strftime('%m/%d/%Y'),
                    'Description': entry.get('description') or f"{entry['vendor']} POS {self._random_location_suffix()}",
                    'Amount': amount
                })
                month_total += abs(amount)
            if month_total <= 0:
                continue
            month_start = self._month_start(month)
            dim = self._days_in_month(month_start)
            payment_date = month_start + timedelta(days=max(0, dim - random.randint(2, 4)))
            label = random.choice(self.credit_card_payment_labels)
            payments.append({
                'date': payment_date,
                'amount': round(month_total, 2),
                'label': label
            })
        card_rows.sort(key=lambda x: datetime.strptime(x['Date'], '%m/%d/%Y'))
        cc_df = pd.DataFrame(card_rows)
        return {'transactions': cc_df, 'payments': payments}
    
    def _random_location_suffix(self) -> str:
        return random.choice(self.location_suffixes)

    def _choose_state(self) -> str:
        region = str(self.config.get('region', 'mixed') or 'mixed').strip().lower()
        if region in ('mixed', 'national'):
            return random.choice(self.us_states)
        if len(region) == 2 and region.upper() in self.us_states:
            return region.upper()
        legacy_regions = {
            'southwest': ['AZ', 'NM', 'NV'],
            'texas': ['TX'],
            'california': ['CA']
        }
        if region in legacy_regions:
            return random.choice(legacy_regions[region])
        # Fall back to mixed national
        return random.choice(self.us_states)

    def _compose_bank_description(self, is_deposit: bool, customer_names: List[str], vendor_names: List[str]) -> str:
        vendor_pool = vendor_names + self.extra_vendor_names
        if is_deposit:
            customer_pool = customer_names or vendor_pool or ['Client']
            templates = [
                lambda: f"ACH Payment - {random.choice(customer_pool)}",
                lambda: f"Stripe Payout {random.randint(1000, 9999)}",
                lambda: f"Square Settlement {datetime.now().strftime('%m%d')}",
                lambda: f"Deposit from {random.choice(customer_pool)}",
                lambda: f"Incoming Wire - {random.choice(customer_pool)}"
            ]
        else:
            vendor_pool = vendor_pool or ['Operating Expense']
            templates = [
                lambda: f"{random.choice(vendor_pool)} POS {self._random_location_suffix()}",
                lambda: f"{random.choice(vendor_pool)} ACH Debit",
                lambda: f"{random.choice(vendor_pool)} ePayment",
                lambda: f"Check #{random.randint(3000, 4999)} {random.choice(vendor_pool)}",
                lambda: f"{random.choice(vendor_pool)} Subscription"
            ]
        # Evaluate template and ensure no stray walrus variables left behind
        desc = random.choice(templates)()
        return desc

    def _compose_credit_card_description(self, vendor_names: List[str]) -> str:
        vendor_pool = vendor_names + self.extra_vendor_names or ['Card Purchase']
        templates = [
            lambda: f"{random.choice(vendor_pool)} POS {self._random_location_suffix()}",
            lambda: f"{random.choice(vendor_pool)} Online",
            lambda: f"{random.choice(vendor_pool)} Subscription",
            lambda: f"{random.choice(vendor_pool)} Fuel",
            lambda: f"{random.choice(vendor_pool)} Travel"
        ]
        return random.choice(templates)()

    def _fallback_product_name(self, industry: str, idx: int) -> str:
        fallback_names = {
            'wellness': [
                'Wellness Package', 'Therapy Bundle', 'Studio Membership', 'Aromatherapy Blend',
                'Herbal Supplement', 'Wellness Guide', 'Meditation Cushion', 'Reiki Session',
                'Acupuncture Treatment', 'Holistic Consultation', 'Wellness Retreat', 'Detox Program',
                'Fitness Training', 'Personal Training', 'Massage Oil', 'Yoga Accessories',
                'Wellness Book', 'Stress Relief Kit', 'Sleep Support', 'Energy Boost'
            ],
            'retail': [
                'Merchandise Bundle', 'Retail Collection', 'Seasonal Assortment', 'Gift Set',
                'Limited Edition', 'Best Seller', 'New Arrival', 'Classic Style',
                'Premium Selection', 'Value Pack', 'Special Edition', 'Trending Item',
                'Customer Favorite', 'Top Seller', 'Exclusive Item', 'Featured Product'
            ],
            'ecommerce': [
                'Digital Bundle', 'Subscription Plan', 'Premium Access', 'Online Resource',
                'Digital Guide', 'E-learning Course', 'Download Package', 'Virtual Workshop',
                'Cloud Service', 'SaaS Subscription', 'Digital Toolkit', 'Online Training'
            ],
            'restaurant': [
                'Chef Special', 'Catering Package', 'Seasonal Menu', 'Daily Special',
                'Signature Dish', 'House Favorite', 'Chef Recommendation', 'Today Special',
                'Seasonal Item', 'Featured Entree', 'Popular Choice', 'Weekly Special'
            ],
            'services': [
                'Consulting Package', 'Service Plan', 'Support Block', 'Expert Consultation',
                'Professional Service', 'Advisory Session', 'Implementation Service', 'Strategy Session'
            ],
            'nonprofit': [
                'Fundraising Kit', 'Program Package', 'Community Bundle', 'Outreach Program',
                'Community Service', 'Volunteer Package', 'Donation Bundle', 'Awareness Campaign'
            ],
            'custom': [
                'Custom Offering', 'Tailored Package', 'Client Bundle', 'Specialized Service',
                'Custom Solution', 'Tailored Product', 'Client Specific', 'Bespoke Offering'
            ]
        }
        bases = fallback_names.get(industry, fallback_names['custom'])
        # Cycle through the list to avoid numbers, using idx to pick different items
        base = bases[idx % len(bases)]
        # If we've exhausted the list, add a descriptive word rather than a number
        if idx >= len(bases):
            descriptors = ['Deluxe', 'Standard', 'Basic', 'Advanced', 'Professional', 'Premium', 'Essential']
            descriptor = descriptors[(idx // len(bases)) % len(descriptors)]
            # Avoid simple numbering by using descriptive prefixes
            if base not in self.used_product_names:
                return base
            return f"{descriptor} {base}"
        return base

    def _unique_product_name(self, base_name: str) -> str:
        candidate = base_name.strip()
        if candidate not in self.used_product_names:
            self.used_product_names.add(candidate)
            return candidate
        suffixes = ['Bundle', 'Pack', 'Set', 'Plus', 'Premium', self.client_code]
        counter = 2
        while True:
            suffix = random.choice(suffixes)
            variant = f"{candidate} ({suffix} {counter})"
            if variant not in self.used_product_names:
                self.used_product_names.add(variant)
                return variant
            counter += 1

    def _product_description(self, name: str, industry: str, product_type: str) -> str:
        library = {
            'wellness': {
                # Services
                'Massage Therapy Session': [
                    '60-minute therapeutic massage focused on relieving muscle tension and stress.',
                    'Customized massage session with aromatherapy add-on for targeted pain relief.'
                ],
                'Yoga Class': [
                    'Instructor-led vinyasa flow session suitable for all experience levels.',
                    'Small group yoga class emphasizing breathwork, balance, and flexibility.'
                ],
                'Nutrition Consultation': [
                    'One-on-one nutrition coaching session with personalized meal planning guidance.',
                    'Comprehensive dietary review with actionable recommendations for the next 30 days.'
                ],
                'Meditation Workshop': [
                    'Guided meditation session designed to promote relaxation and mindfulness.',
                    'Group meditation workshop focusing on stress reduction and inner peace.'
                ],
                'Reiki Session': [
                    'Energy healing session to promote balance and reduce stress.',
                    'Traditional Reiki treatment focusing on restoring natural energy flow.'
                ],
                'Acupuncture Treatment': [
                    'Traditional acupuncture session for pain relief and wellness.',
                    'Acupuncture treatment targeting specific health concerns with fine needles.'
                ],
                'Holistic Consultation': [
                    'Comprehensive wellness consultation covering multiple health dimensions.',
                    'Whole-person approach consultation integrating mind, body, and spirit.'
                ],
                'Sound Healing Session': [
                    'Therapeutic sound session using singing bowls and instruments.',
                    'Vibrational healing experience designed to restore balance and harmony.'
                ],
                'Pilates Class': [
                    'Mat-based Pilates class focusing on core strength and flexibility.',
                    'Instructor-led Pilates session for improved posture and body alignment.'
                ],
                'Tai Chi Class': [
                    'Gentle martial arts class promoting balance, flexibility, and relaxation.',
                    'Traditional Tai Chi session suitable for all fitness levels.'
                ],
                'Reflexology Session': [
                    'Foot reflexology treatment targeting pressure points for overall wellness.',
                    'Hand and foot reflexology session to promote relaxation and healing.'
                ],
                # Products - Non-inventory
                'Essential Oil Set': [
                    'Premium collection of 100% pure essential oils in convenient travel-sized bottles.',
                    'Curated set of therapeutic-grade essential oils with blend suggestions included.'
                ],
                'Yoga Mat': [
                    'High-quality non-slip yoga mat with carrying strap included.',
                    'Eco-friendly yoga mat made from sustainable materials with superior grip.'
                ],
                'Aromatherapy Diffuser': [
                    'Ultrasonic aromatherapy diffuser with LED lighting and timer function.',
                    'Compact essential oil diffuser perfect for home or office use.'
                ],
                'Herbal Tea Collection': [
                    'Assorted selection of organic herbal teas in individually wrapped packets.',
                    'Premium herbal tea blend collection featuring calming and energizing varieties.'
                ],
                'Meditation Cushion': [
                    'Comfortable meditation cushion filled with buckwheat hulls for support.',
                    'Ergonomic zafu cushion designed for proper posture during meditation practice.'
                ],
                'Yoga Block Set': [
                    'Set of two foam yoga blocks for improved alignment and support.',
                    'Lightweight cork yoga blocks perfect for beginners and advanced practitioners.'
                ],
                'Yoga Strap': [
                    'Durable cotton yoga strap with metal D-ring buckle for secure adjustment.',
                    '6-foot yoga strap to help deepen stretches and improve flexibility.'
                ],
                'Foam Roller': [
                    'High-density foam roller for self-myofascial release and muscle recovery.',
                    '18-inch foam roller designed for deep tissue massage and flexibility work.'
                ],
                'Weighted Blanket': [
                    '15-pound weighted blanket filled with glass beads for stress relief.',
                    'Premium weighted blanket designed to promote better sleep and relaxation.'
                ],
                'Massage Oil Bottle': [
                    '4-ounce bottle of therapeutic massage oil with natural ingredients.',
                    'Unscented massage oil perfect for therapeutic bodywork and relaxation.'
                ],
                'Healing Crystal Set': [
                    'Collection of polished healing crystals with guidebook included.',
                    'Premium crystal set including amethyst, rose quartz, and clear quartz stones.'
                ],
                'Wellness Journal': [
                    'Daily wellness journal with prompts for gratitude and reflection.',
                    'Structured journal designed to track mood, habits, and wellness goals.'
                ],
                'CBD Oil Tincture': [
                    'Full-spectrum CBD oil tincture in 30ml bottle with dropper.',
                    'Premium CBD oil extract available in multiple strengths for wellness support.'
                ],
                'Supplements Bundle': [
                    'Comprehensive vitamin and mineral supplement pack for daily wellness.',
                    'Curated supplement bundle featuring essential nutrients for optimal health.'
                ],
                '_generic_service': [
                    'Service delivered by our certified wellness team with flexible scheduling.',
                    'Curated wellness experience designed to support client lifestyle goals.'
                ],
                '_generic_product': [
                    'High-quality wellness product sourced from trusted suppliers.',
                    'Premium wellness item designed to support your health and wellbeing journey.'
                ]
            },
            'retail': {
                'Wireless Headphones': [
                    'Bluetooth headphones with noise cancellation and 30-hour battery life.',
                    'Premium wireless over-ear headphones featuring superior sound quality.'
                ],
                'Smart Watch': [
                    'Fitness tracking smartwatch with heart rate monitor and GPS capabilities.',
                    'Advanced smartwatch with health sensors, notifications, and app support.'
                ],
                'Phone Case': [
                    'Durable protective case with raised edges for screen protection.',
                    'Slim phone case with shock absorption and clear design.'
                ],
                'Charging Cable': [
                    'Fast-charging USB-C cable with reinforced connector ends.',
                    '6-foot charging cable compatible with multiple device types.'
                ],
                'Desk Lamp': [
                    'LED desk lamp with adjustable brightness and color temperature.',
                    'Modern desk lamp featuring USB charging port and flexible arm design.'
                ],
                'Coffee Maker': [
                    'Programmable coffee maker with thermal carafe and auto-shutoff.',
                    'Single-serve coffee maker compatible with standard pods and reusable filters.'
                ],
                'Water Bottle': [
                    'Insulated stainless steel water bottle keeps drinks cold for 24 hours.',
                    'BPA-free water bottle with leak-proof lid and carrying handle.'
                ],
                'Backpack': [
                    'Laptop backpack with padded compartment and multiple organizational pockets.',
                    'Durable backpack with water-resistant material and ergonomic shoulder straps.'
                ],
                'Laptop Stand': [
                    'Adjustable aluminum laptop stand for improved ergonomics and airflow.',
                    'Portable laptop stand with foldable design for easy travel.'
                ],
                'Keyboard': [
                    'Mechanical keyboard with RGB backlighting and programmable keys.',
                    'Wireless keyboard with ergonomic design and long battery life.'
                ],
                'Mouse': [
                    'Wireless optical mouse with precision tracking and ergonomic shape.',
                    'Gaming mouse with customizable buttons and adjustable DPI settings.'
                ],
                'Monitor Stand': [
                    'Desktop monitor stand with storage shelf and cable management.',
                    'Adjustable monitor riser to reduce neck strain and improve workspace organization.'
                ],
                'Desk Organizer': [
                    'Multi-compartment desk organizer for pens, papers, and office supplies.',
                    'Bamboo desk organizer with removable dividers for customizable storage.'
                ],
                'Reading Light': [
                    'LED reading light with flexible gooseneck and adjustable brightness.',
                    'Clip-on reading light perfect for books, desks, and bedside tables.'
                ],
                'USB Hub': [
                    '4-port USB hub with fast data transfer and power delivery support.',
                    'Compact USB hub with individual power switches for each port.'
                ],
                'Laptop Sleeve': [
                    'Padded laptop sleeve with front pocket and carrying handle.',
                    'Neoprene laptop case with water-resistant material and zipper closure.'
                ],
                'Wall Clock': [
                    'Modern wall clock with silent movement and clear number display.',
                    'Decorative wall clock with battery-operated mechanism and easy-to-read face.'
                ],
                'Picture Frame': [
                    'Glass picture frame with matting for 5x7 inch photos.',
                    'Wooden picture frame available in multiple finishes and sizes.'
                ],
                'Candle Set': [
                    'Set of three scented candles with varying aromas for home ambiance.',
                    'Premium soy candle collection with long burn time and natural fragrances.'
                ],
                'Throw Pillow': [
                    'Decorative throw pillow with removable cover for easy washing.',
                    'Accent pillow with premium fabric and comfortable fill material.'
                ],
                'Kitchen Knife Set': [
                    'Professional knife set with wooden block and sharpening steel.',
                    'Stainless steel knife collection with ergonomic handles and protective storage.'
                ],
                'Cutting Board': [
                    'Bamboo cutting board with juice groove and non-slip feet.',
                    'Durable cutting board with antibacterial properties and easy maintenance.'
                ],
                'Storage Container Set': [
                    'Airtight food storage containers in various sizes with stackable design.',
                    'BPA-free plastic containers with secure lids for pantry organization.'
                ],
                'Utensil Set': [
                    'Complete utensil set with serving spoons, spatulas, and tongs.',
                    'Stainless steel cooking utensils with heat-resistant handles and hanging storage.'
                ],
                'Tablecloth': [
                    'Machine-washable tablecloth with stain-resistant finish.',
                    'Elegant table covering available in multiple sizes and colors.'
                ],
                '_generic': [
                    'Quality retail product with reliable performance and customer satisfaction.',
                    'Popular retail item featuring durable construction and excellent value.'
                ]
            },
            'ecommerce': {
                'Online Course': [
                    'Video-based training course with downloadable worksheets and guided exercises.',
                    'Self-paced online curriculum featuring expert-led demonstrations.'
                ],
                'Digital Product': [
                    'Downloadable asset delivered instantly upon purchase.',
                    'Digital resource pack that includes templates, checklists, and tutorials.'
                ],
                'Monthly Subscription': [
                    'Recurring monthly subscription with automatic renewal and cancellation options.',
                    'Subscription service with access to exclusive content and regular updates.'
                ],
                'Video Training Series': [
                    'Comprehensive video training series with lifetime access and bonus materials.',
                    'Multi-part video course covering essential topics with downloadable resources.'
                ],
                'E-book Download': [
                    'Instant digital download in multiple formats including PDF and EPUB.',
                    'Comprehensive e-book with actionable insights and practical examples.'
                ],
                'Software License': [
                    'Software license with full version access and technical support included.',
                    'Annual software license including updates and customer support.'
                ],
                'Template Pack': [
                    'Collection of professional templates ready for immediate use.',
                    'Premium template bundle with customizable designs and commercial license.'
                ],
                'Online Workshop': [
                    'Live online workshop with interactive Q&A and recording access.',
                    'Virtual workshop session with expert instruction and downloadable materials.'
                ],
                'Masterclass Access': [
                    'Exclusive masterclass with industry expert instruction and community access.',
                    'Premium masterclass featuring in-depth training and bonus resources.'
                ],
                'Digital Planner': [
                    'Printable digital planner compatible with tablets and note-taking apps.',
                    'Comprehensive digital planner with monthly, weekly, and daily layouts.'
                ],
                'PDF Guide': [
                    'Detailed PDF guide with step-by-step instructions and illustrations.',
                    'Comprehensive guide available for instant download in PDF format.'
                ],
                'Webinar Recording': [
                    'Recorded webinar with presentation slides and supplementary materials.',
                    'On-demand webinar access with lifetime viewing rights.'
                ],
                'Online Certification': [
                    'Professional certification program with exam and certificate upon completion.',
                    'Industry-recognized certification with training materials and assessment.'
                ],
                'App Subscription': [
                    'Monthly app subscription with premium features and regular updates.',
                    'App access with ad-free experience and exclusive functionality.'
                ],
                'Cloud Storage Plan': [
                    'Cloud storage subscription with automatic backup and file synchronization.',
                    'Secure cloud storage with encrypted files and multi-device access.'
                ],
                'Design Assets Bundle': [
                    'Collection of design assets including icons, graphics, and fonts.',
                    'Premium design bundle with commercial-use license and regular additions.'
                ],
                'Stock Photo Pack': [
                    'Curated collection of high-resolution stock photos for commercial use.',
                    'Professional stock photo bundle with royalty-free license included.'
                ],
                'Online Coaching': [
                    'One-on-one online coaching sessions with personalized action plans.',
                    'Coaching program with regular sessions and ongoing support.'
                ],
                'Virtual Consulting': [
                    'Video consultation service with flexible scheduling and follow-up support.',
                    'Expert virtual consulting with comprehensive analysis and recommendations.'
                ],
                'Membership Site Access': [
                    'Premium membership with exclusive content and community access.',
                    'Membership subscription with monthly updates and member benefits.'
                ],
                '_generic': [
                    'Digital product delivered instantly with lifetime access.',
                    'Online service with flexible access and comprehensive support.'
                ]
            },
            'restaurant': {
                'Lunch Special': [
                    'Chef-prepared lunch entrée served with seasonal sides and beverage.',
                    'Midday combo featuring rotating menu selections and fresh ingredients.'
                ],
                'Dinner Entree': [
                    'Evening entrée crafted with locally sourced ingredients and house-made sauces.',
                    'Signature dinner plate paired with chef-recommended wine options.'
                ],
                'Appetizer': [
                    'Starter dish featuring fresh ingredients and house-made accompaniments.',
                    'Small plate designed to share with unique flavor combinations.'
                ],
                'Dessert': [
                    'House-made dessert using seasonal ingredients and classic techniques.',
                    'Indulgent sweet ending to your meal with daily rotating selections.'
                ],
                'Soup of the Day': [
                    'Daily soup featuring seasonal produce and house-made stock.',
                    'Chef\'s daily soup creation with fresh ingredients and bold flavors.'
                ],
                'Salad': [
                    'Fresh salad with mixed greens, seasonal vegetables, and house dressing.',
                    'Crisp salad featuring locally sourced produce and premium toppings.'
                ],
                'Sandwich': [
                    'Artisan sandwich on house-made bread with premium ingredients.',
                    'Hearty sandwich with your choice of protein and fresh accompaniments.'
                ],
                'Breakfast Plate': [
                    'Complete breakfast plate with eggs, sides, and toast.',
                    'Satisfying morning meal with fresh ingredients and generous portions.'
                ],
                'Kids Meal': [
                    'Kid-friendly meal option with side and beverage included.',
                    'Specially portioned children\'s meal with healthy and appealing choices.'
                ],
                'Vegetarian Option': [
                    'Plant-based dish featuring seasonal vegetables and flavorful preparations.',
                    'Wholesome vegetarian entrée with protein-rich ingredients and bold spices.'
                ],
                'Chef Special': [
                    'Chef\'s daily special showcasing seasonal ingredients and culinary creativity.',
                    'Unique dish prepared daily with limited availability and exceptional quality.'
                ],
                'Seafood Dish': [
                    'Fresh seafood entrée prepared with sustainable sourcing and expert technique.',
                    'Premium fish dish featuring daily catch and complementary accompaniments.'
                ],
                'Pasta Dish': [
                    'House-made pasta with seasonal sauces and premium ingredients.',
                    'Authentic pasta preparation with imported ingredients and traditional methods.'
                ],
                'Pizza': [
                    'Artisan pizza with house-made dough and fresh toppings.',
                    'Wood-fired pizza with premium ingredients and customizable options.'
                ],
                'Side Dish': [
                    'Complimentary side item to enhance your main course.',
                    'Seasonal side dish featuring fresh ingredients and classic preparations.'
                ],
                'Beverage': [
                    'Selection of non-alcoholic beverages including soft drinks and juices.',
                    'Refreshing beverage choice to complement your meal.'
                ],
                'Coffee': [
                    'Freshly brewed coffee using premium beans and traditional methods.',
                    'Artisan coffee with options for espresso, cappuccino, and specialty drinks.'
                ],
                'Tea': [
                    'Selection of premium teas including herbal and traditional varieties.',
                    'Quality tea service with loose leaf options and proper brewing.'
                ],
                'Juice': [
                    'Freshly squeezed juice using seasonal fruits and vegetables.',
                    'Premium juice selection with cold-pressed options and custom blends.'
                ],
                'Wine Glass': [
                    'Premium wine selection by the glass with rotating varietals.',
                    'Curated wine list featuring regional and international selections.'
                ],
                'Cocktail': [
                    'Craft cocktail made with premium spirits and house-made mixers.',
                    'Signature cocktail creation featuring unique flavor combinations.'
                ],
                'Beer': [
                    'Selection of craft beers on tap and bottled options.',
                    'Curated beer menu featuring local and imported selections.'
                ],
                '_generic': [
                    'Menu item prepared to order using fresh, locally sourced produce.',
                    'Kitchen specialty created to showcase seasonal flavors.'
                ]
            },
            'services': {
                'Consulting Hour': [
                    'Hourly consulting engagement focused on immediate business priorities.',
                    'Strategic advisory session with follow-up action items.'
                ],
                'Project Management': [
                    'Dedicated project oversight with milestone tracking and status reporting.',
                    'End-to-end project coordination with weekly stakeholder updates.'
                ],
                'Technical Support': [
                    'Technical assistance with troubleshooting and problem resolution.',
                    'Expert technical support with remote access and follow-up documentation.'
                ],
                'Web Development': [
                    'Custom website development with responsive design and modern technologies.',
                    'Professional web development service including design, coding, and testing.'
                ],
                'Graphic Design': [
                    'Professional graphic design service for marketing materials and branding.',
                    'Custom design work including logos, layouts, and visual identity elements.'
                ],
                'Content Writing': [
                    'Professional content writing service for websites, blogs, and marketing.',
                    'SEO-optimized content creation with research and editing included.'
                ],
                'SEO Audit': [
                    'Comprehensive SEO audit with actionable recommendations and implementation guide.',
                    'Detailed website analysis focusing on search engine optimization opportunities.'
                ],
                'Social Media Management': [
                    'Complete social media management including content creation and engagement.',
                    'Social media strategy and execution with monthly reporting and analytics.'
                ],
                'Marketing Strategy': [
                    'Strategic marketing plan development with competitive analysis and recommendations.',
                    'Comprehensive marketing strategy session with implementation roadmap.'
                ],
                'Business Coaching': [
                    'One-on-one business coaching to help achieve professional and personal goals.',
                    'Structured coaching program with accountability and progress tracking.'
                ],
                'Legal Consultation': [
                    'Legal consultation service with expert advice on business matters.',
                    'Professional legal guidance with document review and strategy recommendations.'
                ],
                'Accounting Service': [
                    'Professional accounting services including bookkeeping and financial reporting.',
                    'Comprehensive accounting support with monthly financial statements.'
                ],
                'Bookkeeping': [
                    'Monthly bookkeeping service with transaction recording and reconciliation.',
                    'Accurate bookkeeping with organized records and financial categorization.'
                ],
                'Tax Preparation': [
                    'Tax preparation service with filing support and optimization strategies.',
                    'Professional tax return preparation with audit protection and advice.'
                ],
                'Translation Service': [
                    'Professional translation service for documents and content in multiple languages.',
                    'Accurate translation with native speaker review and quality assurance.'
                ],
                'Photography Session': [
                    'Professional photography session with edited high-resolution images delivered.',
                    'Custom photography service including location selection and image editing.'
                ],
                'Video Production': [
                    'Complete video production service from concept to final edited product.',
                    'Professional video creation including filming, editing, and post-production.'
                ],
                'Event Planning': [
                    'Full-service event planning from initial concept to day-of coordination.',
                    'Comprehensive event management with vendor coordination and timeline execution.'
                ],
                'Virtual Assistant': [
                    'Remote virtual assistant service for administrative and operational tasks.',
                    'Dedicated virtual assistant support with flexible hours and task management.'
                ],
                'Data Entry': [
                    'Accurate data entry service with quality checks and organized delivery.',
                    'Efficient data processing with attention to detail and format specifications.'
                ],
                '_generic': [
                    'Professional service engagement delivered by our senior team.',
                    'Billable service block with defined scope and deliverables.'
                ]
            }
        }
        industry_key = industry if industry in library else 'services'
        entries = library[industry_key]
        # Check for exact name match first
        if name in entries:
            options = entries[name]
        # Then check for product type with industry-specific generic
        elif product_type == 'Service' and '_generic_service' in entries:
            options = entries['_generic_service']
        elif product_type == 'Non-inventory' and '_generic_product' in entries:
            options = entries['_generic_product']
        # Fall back to general generic
        elif '_generic' in entries:
            options = entries['_generic']
        else:
            options = ['Product offering tailored to client requirements.', 'Standard catalog item with consistent demand.']
        return random.choice(options)

    def generate(self, output_dir: str) -> str:
        """Main generation method"""
        try:
            # Create working directory inside output_dir
            workdir = os.path.join(output_dir, "workdir")
            self.ensure_dir(workdir)
            logger.info(f"Created work directory: {workdir}")
            
            # Generate core entities first (they need to reference each other)
            self.generated_customers = self.generate_customers()
            self.generated_vendors = self.generate_vendors()
            self.generated_products = self.generate_products()
            self.generated_invoices = self.generate_invoices()
            self._simulate_sales_activity()
            self.expense_occurrences = self._expand_expense_templates()
            self.personal_expenses = self._plan_misc_personal_purchases()
            self.invoice_payments = self._plan_invoice_payments()
            self.savings_transfers = self._schedule_savings_transfers()
            self.misc_bank_withdrawals = self._plan_misc_bank_withdrawals()
            self.credit_card_plan = self.plan_credit_card_activity()
            
            # Create all requested data
            datasets = {}
            bank_data = None
            
            if 'customers' in self.config.get('output_files', []):
                datasets['customers'] = self.generated_customers
            
            if 'vendors' in self.config.get('output_files', []):
                datasets['vendors'] = self.generated_vendors
            
            if 'products' in self.config.get('output_files', []):
                datasets['products'] = self.generated_products
            
            if 'chart_of_accounts' in self.config.get('output_files', []):
                datasets['chart_of_accounts'] = self.generate_chart_of_accounts()
            
            if 'invoices' in self.config.get('output_files', []):
                datasets['invoices'] = self.generated_invoices
            
            if 'bills' in self.config.get('output_files', []):
                datasets['bills'] = self.generate_bills()
            
            if 'checks' in self.config.get('output_files', []):
                datasets['checks'] = self.generate_checks()
            
            if 'bank' in self.config.get('output_files', []):
                bank_data = self.generate_bank_accounts(self.credit_card_plan.get('payments'))
                datasets['bank_accounts'] = bank_data['transactions']
                datasets['credit_cards'] = self.credit_card_plan['transactions']
            
            elif 'creditcard' in self.config.get('output_files', []):
                datasets['credit_cards'] = self.credit_card_plan['transactions']
            
            if 'savings' in self.config.get('output_files', []) and self.config.get('include_savings_account'):
                transfers = bank_data.get('savings_transfers') if bank_data else self.savings_transfers
                datasets['savings_accounts'] = self.generate_savings_accounts(transfers)
            
            # Save datasets to files
            self.save_datasets(datasets, workdir)
            
            # Create ZIP file
            zip_path = self.create_zip(workdir, output_dir)
            
            return zip_path
            
        except Exception as e:
            logger.error(f"Generation error: {e}")
            raise
    
    def generate_customers(self) -> pd.DataFrame:
        # Respect business scale settings if present, otherwise use provided value
        n = int(self.config.get('num_customers', 0) or 0)
        if n <= 0:
            # fallback to a safe default
            n = 10
        customers = []
        for i in range(n):
            # Choose state depending on configured region bias
            state = self._choose_state()
            city = self.faker.city()
            zip_code = self.faker.zipcode()
            address = f"{self.faker.street_address()}, {city}, {state} {zip_code}"
            
            # Ensure phone length does not exceed 21 characters
            phone = str(self.faker.phone_number())[:21]
            customers.append({
                'Display Name': self.faker.company() if random.random() > 0.3 else f"{self.faker.first_name()} {self.faker.last_name()}",
                'Company': '',
                'Email': self.faker.email(),
                'Phone': phone,
                'Billing Address': address
            })
        return pd.DataFrame(customers)
    
    def generate_vendors(self) -> pd.DataFrame:
        n = int(self.config.get('num_vendors', 0) or 0)
        if n <= 0:
            n = 10
        vendors = []
        
        common_vendors = [
            'Office Depot', 'Staples', 'Amazon Business', 'Verizon', 'AT&T', 
            'Comcast', 'FedEx', 'UPS', 'USPS', 'Google Workspace', 
            'Microsoft', 'Adobe', 'Slack', 'Zoom', 'Dropbox'
        ]
        
        for i in range(n):
            if i < len(common_vendors):
                vendor_name = common_vendors[i]
            else:
                vendor_name = self.faker.company()
            
            state = self._choose_state()
            city = self.faker.city()
            zip_code = self.faker.zipcode()
            address = f"{self.faker.street_address()}, {city}, {state} {zip_code}"
            
            # Ensure phone length does not exceed 21 characters
            phone = str(self.faker.phone_number())[:21]
            vendors.append({
                'Display Name': vendor_name,
                'Company': vendor_name,
                'Email': self.faker.company_email(),
                'Phone': phone,
                'Billing Address': address
            })
        return pd.DataFrame(vendors)
    
    def generate_products(self) -> pd.DataFrame:
        n = self.config['num_products']
        industry = self.config['industry']
        products = []
        
        product_templates = {
            'wellness': [
                {'name': 'Massage Therapy Session', 'type': 'Service', 'price_range': (80, 150)},
                {'name': 'Yoga Class', 'type': 'Service', 'price_range': (20, 40)},
                {'name': 'Nutrition Consultation', 'type': 'Service', 'price_range': (75, 125)},
                {'name': 'Meditation Workshop', 'type': 'Service', 'price_range': (50, 100)},
                {'name': 'Essential Oil Set', 'type': 'Non-inventory', 'price_range': (25, 60)},
                {'name': 'Yoga Mat', 'type': 'Non-inventory', 'price_range': (30, 80)},
                {'name': 'Aromatherapy Diffuser', 'type': 'Non-inventory', 'price_range': (35, 75)},
                {'name': 'Herbal Tea Collection', 'type': 'Non-inventory', 'price_range': (15, 45)},
                {'name': 'Meditation Cushion', 'type': 'Non-inventory', 'price_range': (40, 90)},
                {'name': 'Reiki Session', 'type': 'Service', 'price_range': (60, 120)},
                {'name': 'Acupuncture Treatment', 'type': 'Service', 'price_range': (75, 140)},
                {'name': 'Holistic Consultation', 'type': 'Service', 'price_range': (80, 150)},
                {'name': 'Yoga Block Set', 'type': 'Non-inventory', 'price_range': (20, 50)},
                {'name': 'Yoga Strap', 'type': 'Non-inventory', 'price_range': (12, 35)},
                {'name': 'Foam Roller', 'type': 'Non-inventory', 'price_range': (25, 65)},
                {'name': 'Weighted Blanket', 'type': 'Non-inventory', 'price_range': (70, 150)},
                {'name': 'Massage Oil Bottle', 'type': 'Non-inventory', 'price_range': (18, 45)},
                {'name': 'Healing Crystal Set', 'type': 'Non-inventory', 'price_range': (30, 85)},
                {'name': 'Wellness Journal', 'type': 'Non-inventory', 'price_range': (15, 40)},
                {'name': 'Sound Healing Session', 'type': 'Service', 'price_range': (55, 110)},
                {'name': 'Pilates Class', 'type': 'Service', 'price_range': (25, 50)},
                {'name': 'Tai Chi Class', 'type': 'Service', 'price_range': (20, 45)},
                {'name': 'Reflexology Session', 'type': 'Service', 'price_range': (50, 100)},
                {'name': 'CBD Oil Tincture', 'type': 'Non-inventory', 'price_range': (40, 95)},
                {'name': 'Supplements Bundle', 'type': 'Non-inventory', 'price_range': (35, 80)},
            ],
            'retail': [
                {'name': 'Wireless Headphones', 'type': 'Non-inventory', 'price_range': (50, 200)},
                {'name': 'Smart Watch', 'type': 'Non-inventory', 'price_range': (100, 400)},
                {'name': 'Phone Case', 'type': 'Non-inventory', 'price_range': (15, 50)},
                {'name': 'Charging Cable', 'type': 'Non-inventory', 'price_range': (10, 35)},
                {'name': 'Desk Lamp', 'type': 'Non-inventory', 'price_range': (25, 80)},
                {'name': 'Coffee Maker', 'type': 'Non-inventory', 'price_range': (40, 150)},
                {'name': 'Water Bottle', 'type': 'Non-inventory', 'price_range': (12, 40)},
                {'name': 'Backpack', 'type': 'Non-inventory', 'price_range': (30, 100)},
                {'name': 'Laptop Stand', 'type': 'Non-inventory', 'price_range': (20, 70)},
                {'name': 'Keyboard', 'type': 'Non-inventory', 'price_range': (25, 120)},
                {'name': 'Mouse', 'type': 'Non-inventory', 'price_range': (15, 60)},
                {'name': 'Monitor Stand', 'type': 'Non-inventory', 'price_range': (20, 65)},
                {'name': 'Desk Organizer', 'type': 'Non-inventory', 'price_range': (15, 50)},
                {'name': 'Reading Light', 'type': 'Non-inventory', 'price_range': (18, 55)},
                {'name': 'USB Hub', 'type': 'Non-inventory', 'price_range': (20, 60)},
                {'name': 'Laptop Sleeve', 'type': 'Non-inventory', 'price_range': (18, 50)},
                {'name': 'Wall Clock', 'type': 'Non-inventory', 'price_range': (15, 75)},
                {'name': 'Picture Frame', 'type': 'Non-inventory', 'price_range': (10, 45)},
                {'name': 'Candle Set', 'type': 'Non-inventory', 'price_range': (12, 40)},
                {'name': 'Throw Pillow', 'type': 'Non-inventory', 'price_range': (15, 50)},
                {'name': 'Kitchen Knife Set', 'type': 'Non-inventory', 'price_range': (40, 120)},
                {'name': 'Cutting Board', 'type': 'Non-inventory', 'price_range': (20, 60)},
                {'name': 'Storage Container Set', 'type': 'Non-inventory', 'price_range': (15, 55)},
                {'name': 'Utensil Set', 'type': 'Non-inventory', 'price_range': (18, 50)},
                {'name': 'Tablecloth', 'type': 'Non-inventory', 'price_range': (20, 65)},
            ],
            'ecommerce': [
                {'name': 'Online Course', 'type': 'Service', 'price_range': (99, 299)},
                {'name': 'Digital Product', 'type': 'Non-inventory', 'price_range': (19, 79)},
                {'name': 'Monthly Subscription', 'type': 'Service', 'price_range': (29, 99)},
                {'name': 'Video Training Series', 'type': 'Service', 'price_range': (149, 399)},
                {'name': 'E-book Download', 'type': 'Non-inventory', 'price_range': (9, 49)},
                {'name': 'Software License', 'type': 'Non-inventory', 'price_range': (49, 299)},
                {'name': 'Template Pack', 'type': 'Non-inventory', 'price_range': (15, 65)},
                {'name': 'Online Workshop', 'type': 'Service', 'price_range': (79, 199)},
                {'name': 'Masterclass Access', 'type': 'Service', 'price_range': (199, 499)},
                {'name': 'Digital Planner', 'type': 'Non-inventory', 'price_range': (12, 35)},
                {'name': 'PDF Guide', 'type': 'Non-inventory', 'price_range': (8, 29)},
                {'name': 'Webinar Recording', 'type': 'Non-inventory', 'price_range': (29, 99)},
                {'name': 'Online Certification', 'type': 'Service', 'price_range': (299, 799)},
                {'name': 'App Subscription', 'type': 'Service', 'price_range': (9, 49)},
                {'name': 'Cloud Storage Plan', 'type': 'Service', 'price_range': (5, 25)},
                {'name': 'Design Assets Bundle', 'type': 'Non-inventory', 'price_range': (25, 89)},
                {'name': 'Stock Photo Pack', 'type': 'Non-inventory', 'price_range': (19, 59)},
                {'name': 'Online Coaching', 'type': 'Service', 'price_range': (99, 299)},
                {'name': 'Virtual Consulting', 'type': 'Service', 'price_range': (75, 250)},
                {'name': 'Membership Site Access', 'type': 'Service', 'price_range': (29, 149)},
            ],
            'restaurant': [
                {'name': 'Lunch Special', 'type': 'Service', 'price_range': (12, 25)},
                {'name': 'Dinner Entree', 'type': 'Service', 'price_range': (18, 35)},
                {'name': 'Beverage', 'type': 'Non-inventory', 'price_range': (3, 8)},
                {'name': 'Appetizer', 'type': 'Service', 'price_range': (8, 18)},
                {'name': 'Dessert', 'type': 'Service', 'price_range': (6, 14)},
                {'name': 'Soup of the Day', 'type': 'Service', 'price_range': (7, 15)},
                {'name': 'Salad', 'type': 'Service', 'price_range': (9, 18)},
                {'name': 'Sandwich', 'type': 'Service', 'price_range': (10, 20)},
                {'name': 'Breakfast Plate', 'type': 'Service', 'price_range': (8, 16)},
                {'name': 'Kids Meal', 'type': 'Service', 'price_range': (6, 12)},
                {'name': 'Vegetarian Option', 'type': 'Service', 'price_range': (14, 28)},
                {'name': 'Chef Special', 'type': 'Service', 'price_range': (20, 40)},
                {'name': 'Seafood Dish', 'type': 'Service', 'price_range': (22, 45)},
                {'name': 'Pasta Dish', 'type': 'Service', 'price_range': (15, 32)},
                {'name': 'Pizza', 'type': 'Service', 'price_range': (12, 28)},
                {'name': 'Side Dish', 'type': 'Service', 'price_range': (4, 10)},
                {'name': 'Coffee', 'type': 'Non-inventory', 'price_range': (3, 6)},
                {'name': 'Tea', 'type': 'Non-inventory', 'price_range': (2, 5)},
                {'name': 'Juice', 'type': 'Non-inventory', 'price_range': (4, 8)},
                {'name': 'Wine Glass', 'type': 'Non-inventory', 'price_range': (6, 15)},
                {'name': 'Cocktail', 'type': 'Non-inventory', 'price_range': (8, 18)},
                {'name': 'Beer', 'type': 'Non-inventory', 'price_range': (5, 10)},
            ],
            'services': [
                {'name': 'Consulting Hour', 'type': 'Service', 'price_range': (100, 200)},
                {'name': 'Project Management', 'type': 'Service', 'price_range': (75, 150)},
                {'name': 'Technical Support', 'type': 'Service', 'price_range': (50, 100)},
                {'name': 'Web Development', 'type': 'Service', 'price_range': (80, 180)},
                {'name': 'Graphic Design', 'type': 'Service', 'price_range': (60, 140)},
                {'name': 'Content Writing', 'type': 'Service', 'price_range': (40, 100)},
                {'name': 'SEO Audit', 'type': 'Service', 'price_range': (150, 400)},
                {'name': 'Social Media Management', 'type': 'Service', 'price_range': (500, 2000)},
                {'name': 'Marketing Strategy', 'type': 'Service', 'price_range': (200, 600)},
                {'name': 'Business Coaching', 'type': 'Service', 'price_range': (100, 300)},
                {'name': 'Legal Consultation', 'type': 'Service', 'price_range': (150, 400)},
                {'name': 'Accounting Service', 'type': 'Service', 'price_range': (100, 300)},
                {'name': 'Bookkeeping', 'type': 'Service', 'price_range': (50, 150)},
                {'name': 'Tax Preparation', 'type': 'Service', 'price_range': (200, 600)},
                {'name': 'Translation Service', 'type': 'Service', 'price_range': (30, 80)},
                {'name': 'Photography Session', 'type': 'Service', 'price_range': (200, 800)},
                {'name': 'Video Production', 'type': 'Service', 'price_range': (500, 2500)},
                {'name': 'Event Planning', 'type': 'Service', 'price_range': (300, 1500)},
                {'name': 'Virtual Assistant', 'type': 'Service', 'price_range': (20, 60)},
                {'name': 'Data Entry', 'type': 'Service', 'price_range': (15, 40)},
            ]
        }
        
        template = product_templates.get(industry, product_templates['services'])
        
        for i in range(n):
            if i < len(template):
                product = template[i]
                base_name = product['name']
                price_range = product['price_range']
                product_type = product['type']
            else:
                base_name = self._fallback_product_name(industry, i)
                price_range = (10, 100)
                product_type = 'Service' if random.random() > 0.5 else 'Non-inventory'
            
            name = self._unique_product_name(base_name)
            price = round(random.uniform(price_range[0], price_range[1]), 2)
            sales_desc = self._product_description(name, industry, product_type)
            income_account = 'Service Income' if product_type == 'Service' else 'Sales'
            category = 'Services' if product_type == 'Service' else 'Products'
            sku = f"{self.client_code}-{i+1:03d}"
            products.append({
                'Name': name,
                'Type': product_type,
                'Sales Description': sales_desc,
                'Sales Price/Rate': price,
                'Income Account': income_account,
                'Expense Account': 'Cost of Goods Sold',
                'SKU': sku,
                'Category': category,
                'Taxable': 'Yes',
                'Active': 'Yes'
            })
        return pd.DataFrame(products)
    
    def generate_chart_of_accounts(self) -> pd.DataFrame:
        include_numbers = self.use_account_numbers
        accounts_data = [
            ('Checking Account', 'Bank', 'Checking', '1000', 'Primary checking account for business operations'),
            ('Accounts Receivable', 'Accounts Receivable', 'Accounts Receivable (A/R)', '1200', 'Money owed by customers'),
            ('Credit Card', 'Credit Card', 'Credit Card', '2000', 'Business credit card account'),
            ('Accounts Payable', 'Accounts Payable', 'Accounts Payable (A/P)', '2100', 'Money owed to vendors'),
            ("Owner's Equity", 'Equity', "Owner's Equity", '3000', 'Owner investment in business'),
            ('Sales', 'Income', 'Sales of Product Income', '4000', 'Revenue from product sales'),
            ('Service Income', 'Income', 'Service/Fee Income', '4100', 'Revenue from services provided'),
            ('Cost of Goods Sold', 'Cost of Goods Sold', 'Supplies & Materials - COGS', '5000', 'Direct costs of products sold'),
            ('Rent Expense', 'Expenses', 'Rent or Lease of Building', '6000', 'Office or facility rent'),
            ('Utilities', 'Expenses', 'Utilities', '6100', 'Electricity, water, gas, internet'),
            ('Office Supplies', 'Expenses', 'Office/General Administrative Expenses', '6200', 'Office supplies and materials'),
        ]
        base_accounts: List[Dict] = []
        for name, acc_type, detail, number, description in accounts_data:
            entry = {
                'Name': name,
                'Type': acc_type,
                'Detail Type': detail,
                'Description': description
            }
            if include_numbers:
                entry['Number'] = number
            base_accounts.append(entry)
        
        if self.config.get('include_savings_account'):
            savings_entry = {
                'Name': 'Savings Account',
                'Type': 'Bank',
                'Detail Type': 'Savings',
                'Description': 'Business savings account'
            }
            if include_numbers:
                savings_entry['Number'] = '1010'
            base_accounts.insert(1, savings_entry)
        
        coa_df = pd.DataFrame(base_accounts)
        if not include_numbers and 'Number' in coa_df.columns:
            coa_df = coa_df.drop(columns=['Number'])
        return coa_df
    
    def generate_invoices(self) -> pd.DataFrame:
        n_invoices = self.config['num_invoices']
        if n_invoices == 0:
            return pd.DataFrame()
            
        invoices = []
        start_date = datetime.strptime(self.config['start_date'], '%Y-%m-%d')
        
        customer_records = self.generated_customers.to_dict('records')
        product_records = self.generated_products.to_dict('records')
        
        for i in range(n_invoices):
            inv_date = start_date + timedelta(days=random.randint(0, self.config['months'] * 30 - 1))
            due_date = inv_date + timedelta(days=self.config['invoice_due_days'])
            
            # Pick actual customer and product
            customer = random.choice(customer_records)
            product = random.choice(product_records)
            
            qty = random.randint(1, 10)  # More quantity for larger invoices
            rate = float(product['Sales Price/Rate'])
            amount = round(qty * rate, 2)
            
            invoices.append({
                'Invoice Number': f"INV-{1000 + i}",
                'Customer': customer['Display Name'],
                # QuickBooks prefers MM/DD/YYYY in many import examples
                'Invoice Date': inv_date.strftime('%m/%d/%Y'),
                'Due Date': due_date.strftime('%m/%d/%Y'),
                'Product/Service': product['Name'],
                'Qty': qty,
                'Rate': rate,
                'Amount': amount
            })
        
        return pd.DataFrame(invoices)
    
    def generate_bills(self) -> pd.DataFrame:
        n_bills = max(5, self.config['num_vendors'] // 2)  # Generate bills for about half the vendors
        if n_bills == 0:
            return pd.DataFrame()
            
        bills = []
        start_date = datetime.strptime(self.config['start_date'], '%Y-%m-%d')
        
        vendor_records = self.generated_vendors.to_dict('records')
        expense_accounts = ['Office Supplies', 'Utilities', 'Rent Expense', 'Advertising', 'Professional Fees']
        
        for i in range(n_bills):
            bill_date = start_date + timedelta(days=random.randint(0, self.config['months'] * 30 - 1))
            due_date = bill_date + timedelta(days=30)  # Standard 30-day terms
            
            vendor = random.choice(vendor_records)
            account = random.choice(expense_accounts)
            amount = round(random.uniform(200, 1500), 2)  # Larger bills
            
            bills.append({
                'Bill No': f"BILL-{2000 + i}",
                'Vendor': vendor['Display Name'],
                'Bill Date': bill_date.strftime('%m/%d/%Y'),
                'Due Date': due_date.strftime('%m/%d/%Y'),
                'Account': account,
                'Amount': amount,
                'Memo': f"Payment for {vendor['Display Name']} services"
            })
        
        return pd.DataFrame(bills)
    
    def generate_checks(self) -> pd.DataFrame:
        n_checks = max(3, self.config['bank_txn_per_month'] // 10)  # About 10% of bank transactions as checks
        if n_checks == 0:
            return pd.DataFrame()
            
        checks = []
        start_date = datetime.strptime(self.config['start_date'], '%Y-%m-%d')
        
        vendor_records = self.generated_vendors.to_dict('records')
        expense_accounts = ['Office Supplies', 'Utilities', 'Rent Expense', 'Advertising', 'Professional Fees']
        
        for i in range(n_checks):
            check_date = start_date + timedelta(days=random.randint(0, self.config['months'] * 30 - 1))
            
            vendor = random.choice(vendor_records)
            account = random.choice(expense_accounts)
            amount = round(random.uniform(100, 800), 2)  # Larger checks
            
            checks.append({
                'Check No': f"{3000 + i}",
                'Date': check_date.strftime('%m/%d/%Y'),
                'Payee': vendor['Display Name'],
                'Bank Account': 'Checking Account',
                'Expense Account': account,
                'Amount': amount,
                'Memo': f"Payment to {vendor['Display Name']}"
            })
        
        return pd.DataFrame(checks)
    
    def generate_bank_accounts(self, cc_payments: Optional[List[Dict]] = None) -> Dict:
        entries: List[Dict] = []
        profile = self.industry_profile
        start_balance = round(random.uniform(*profile['starting_balance_range']), 2)
        min_balance = profile['min_balance']
        max_balance = profile['max_balance']
        # Sales deposits and invoice payments
        for deposit in self.sales_deposits:
            entries.append({
                'date': deposit['date'],
                'description': deposit['description'],
                'amount': round(deposit['amount'], 2)
            })
        for payment in self.invoice_payments:
            entries.append({
                'date': payment['date'],
                'description': payment['description'],
                'amount': round(payment['amount'], 2)
            })
        # Refunds (negative)
        for refund in self.refunds:
            entries.append({
                'date': refund['date'],
                'description': refund['description'],
                'amount': round(refund['amount'], 2)
            })
        # ACH/Bank expenses
        for expense in self.expense_occurrences:
            if expense['method'] == 'credit_card':
                continue
            desc = f"{expense['vendor']} ACH Debit" if expense['method'] == 'ach' else f"{expense['vendor']} POS {self._random_location_suffix()}"
            entries.append({
                'date': expense['date'],
                'description': desc,
                'amount': round(-abs(expense['amount']), 2)
            })
        # Personal purchases paid from bank
        for personal in self.personal_expenses:
            if personal['method'] != 'bank':
                continue
            entries.append({
                'date': personal['date'],
                'description': f"{personal['vendor']} POS {self._random_location_suffix()}",
                'amount': round(-abs(personal['amount']), 2)
            })
        # Misc cash withdrawals
        for misc in self.misc_bank_withdrawals:
            entries.append({
                'date': misc['date'],
                'description': misc['description'],
                'amount': round(misc['amount'], 2)
            })
        # Savings transfers
        for transfer in self.savings_transfers:
            if transfer['direction'] == 'to_savings':
                amount = -abs(transfer['amount'])
                desc = 'Transfer to Savings'
            else:
                amount = abs(transfer['amount'])
                desc = 'Transfer from Savings'
            entries.append({
                'date': transfer['date'],
                'description': desc,
                'amount': round(amount, 2)
            })
        # Credit card payments
        if cc_payments:
            for payment in cc_payments:
                entries.append({
                    'date': payment['date'],
                    'description': f"Credit Card Payment - {payment['label']}",
                    'amount': round(-abs(payment['amount']), 2)
                })
        # Sort and manage running balance targets
        entries.sort(key=lambda x: x['date'])
        augmented: List[Dict] = []
        running_balance = start_balance
        midpoint = (min_balance + max_balance) / 2
        for entry in entries:
            running_balance += entry['amount']
            # Owner contribution if balance too low
            if running_balance < min_balance:
                needed = round(midpoint - running_balance, 2)
                if needed > 0:
                    contribution_date = max(entry['date'] - timedelta(days=1), self.start_date)
                    augmented.append({
                        'date': contribution_date,
                        'description': 'Owner Contribution',
                        'amount': needed
                    })
                    running_balance += needed
            # Owner draw if balance too high
            if running_balance > max_balance:
                draw_amount = round(min(running_balance - max_balance * 0.9, random.uniform(1500, 4500)), 2)
                if draw_amount > 0:
                    draw_date = max(entry['date'] - timedelta(days=1), self.start_date)
                    augmented.append({
                        'date': draw_date,
                        'description': 'Owner Draw',
                        'amount': -draw_amount
                    })
                    running_balance -= draw_amount
            augmented.append(entry)
        augmented.sort(key=lambda x: x['date'])
        rows = [{
            'Date': item['date'].strftime('%m/%d/%Y'),
            'Description': item['description'],
            'Amount': round(item['amount'], 2)
        } for item in augmented]
        bank_df = pd.DataFrame(rows)
        return {
            'transactions': bank_df,
            'savings_transfers': self.savings_transfers
        }

    def _apply_messiness_to_df(self, df: pd.DataFrame, file_key: str) -> pd.DataFrame:
        """Introduce small, import-safe imperfections and record them in the answer key."""
        if df.empty:
            return df

        n = len(df)
        override_count = self.error_counts.get(file_key)
        if override_count is not None:
            num_changes = min(max(0, override_count), n)
        else:
            num_changes = max(1, round(n * self.messiness_pct / 100)) if self.messiness_pct > 0 else 0

        # Helper to record an issue
        def record(row_idx: int, msg: str):
            # CSV row number = header (1) + row_idx (0-based) + 1 => row_idx + 2
            csv_row = row_idx + 2
            entry = f"[{file_mapping.get(file_key, file_key)}] Row {csv_row}: {msg}"
            self.answer_key.append(entry)

        # Small set of file-specific messiness patterns
        file_mapping = {
            'customers': 'Customers.csv',
            'vendors': 'Vendors.csv',
            'products': 'Products_and_Services.csv',
            'chart_of_accounts': 'Chart_of_Accounts.csv',
            'invoices': 'Invoices.csv',
            'bank_accounts': 'Bank_Transactions.csv',
            'credit_cards': 'Credit_Card_Transactions.csv'
        }

        df = df.copy()

        if file_key in ('customers', 'vendors') and num_changes > 0:
            indices = random.sample(range(n), k=min(num_changes, n))
            for idx in indices:
                col = random.choice(['Email', 'Phone', 'Display Name'])
                if col == 'Email':
                    df.at[idx, 'Email'] = ''
                    record(idx, 'Missing email')
                elif col == 'Phone':
                    # make phone one digit shorter
                    val = str(df.at[idx, 'Phone'])
                    df.at[idx, 'Phone'] = val[:-1]
                    record(idx, 'Phone number digit missing')
                else:
                    # slight misspelling: remove a character or remove space
                    name = str(df.at[idx, 'Display Name'])
                    if ' ' in name:
                        new = name.replace(' ', '')
                    else:
                        new = name[:-1]
                    df.at[idx, 'Display Name'] = new
                    record(idx, "Display Name misspelled")

        elif file_key == 'products' and num_changes > 0:
            indices = random.sample(range(n), k=min(num_changes, n))
            for idx in indices:
                # remove Sales Description or slightly change price
                if random.random() > 0.5:
                    df.at[idx, 'Sales Description'] = ''
                    record(idx, 'Missing Sales Description')
                else:
                    old = float(df.at[idx, 'Sales Price/Rate'])
                    new = round(old * (1 - random.choice([0.03, 0.02, 0.05])), 2)
                    df.at[idx, 'Sales Price/Rate'] = new
                    record(idx, f'Sales price changed from {old} to {new}')

        elif file_key == 'invoices' and num_changes > 0:
            indices = random.sample(range(n), k=min(num_changes, n))
            for idx in indices:
                # change amount slightly or use customer name variant
                if random.random() > 0.5:
                    old = float(df.at[idx, 'Amount'])
                    new = round(old * (1 - random.choice([0.03, 0.02])), 2)
                    df.at[idx, 'Amount'] = new
                    record(idx, f'Amount {old} changed to {new} (simulated fee)')
                else:
                    cust = str(df.at[idx, 'Customer'])
                    if ' ' in cust:
                        variant = cust.split(' ')[0]
                    else:
                        variant = cust
                    df.at[idx, 'Customer'] = variant
                    record(idx, 'Customer name variant used')

        elif file_key == 'chart_of_accounts' and num_changes > 0:
            indices = random.sample(range(n), k=min(num_changes, n))
            existing_names = df['Name'].tolist() if 'Name' in df.columns else []
            duplicate_candidates = [name for name in existing_names if name in {'Sales', 'Service Income', 'Cost of Goods Sold'}]
            valid_detail_overrides = {
                'Income': ['Sales of Product Income', 'Service/Fee Income', 'Other Primary Income'],
                'Cost of Goods Sold': ['Supplies & Materials - COGS', 'Cost of Sales - Retail', 'Cost of Sales - Labor'],
                'Expenses': ['Office/General Administrative Expenses', 'Advertising/Promotional', 'Utilities', 'Rent or Lease of Building'],
                'Bank': ['Checking', 'Savings'],
                'Credit Card': ['Credit Card'],
                'Accounts Receivable': ['Accounts Receivable (A/R)'],
                'Accounts Payable': ['Accounts Payable (A/P)'],
                'Equity': ["Owner's Equity"]
            }
            for idx in indices:
                action = 'duplicate' if duplicate_candidates and random.random() < 0.7 else 'detail'
                if action == 'duplicate' and 'Name' in df.columns:
                    dup_name = random.choice(duplicate_candidates)
                    df.at[idx, 'Name'] = dup_name
                    if 'Number' in df.columns and self.use_account_numbers:
                        # Reuse the same account number to simulate a duplicate
                        ref_row = next((row for row in range(n) if row != idx and df.at[row, 'Name'] == dup_name), None)
                        if ref_row is not None:
                            df.at[idx, 'Number'] = df.at[ref_row, 'Number']
                    record(idx, f'Duplicate account name "{dup_name}" created')
                else:
                    account_type = df.at[idx, 'Type'] if 'Type' in df.columns else ''
                    detail_options = valid_detail_overrides.get(account_type, [])
                    if detail_options and 'Detail Type' in df.columns:
                        current_detail = df.at[idx, 'Detail Type']
                        alternatives = [opt for opt in detail_options if opt != current_detail] or detail_options
                        new_detail = random.choice(alternatives)
                        df.at[idx, 'Detail Type'] = new_detail
                        record(idx, f'Detail Type switched to "{new_detail}"')
                    elif 'Number' in df.columns and self.use_account_numbers:
                        current_number = df.at[idx, 'Number']
                        if isinstance(current_number, str) and current_number:
                            if current_number[-1].isdigit():
                                new_number = current_number[:-1] + str(random.randint(0, 9))
                            else:
                                new_number = f"{current_number}{random.randint(1, 9)}"
                            df.at[idx, 'Number'] = new_number
                            record(idx, f'Account number changed from {current_number} to {new_number}')
                    else:
                        record(idx, 'Chart of Accounts anomaly added')

        elif file_key in ('bank_accounts', 'credit_cards') and num_changes > 0:
            indices = random.sample(range(n), k=min(num_changes, n))
            for idx in indices:
                # Slight amount change or description typo
                if random.random() > 0.5:
                    old = float(df.at[idx, 'Amount'])
                    new = round(old + random.choice([-3.5, -1.2, 2.1]), 2)
                    df.at[idx, 'Amount'] = new
                    record(idx, f'Amount {old} changed to {new}')
                else:
                    desc = str(df.at[idx, 'Description'])
                    if len(desc) > 5:
                        new = desc.replace(' ', '')[:max(5, len(desc)-2)]
                    else:
                        new = desc
                    df.at[idx, 'Description'] = new
                    record(idx, 'Description shortened or typo introduced')

        # Inject invoices that reference customers not in the master list
        if file_key == 'invoices' and self._invoice_new_customers_remaining > 0:
            known_customers = set()
            if isinstance(self.generated_customers, pd.DataFrame) and not self.generated_customers.empty:
                known_customers = set(self.generated_customers['Display Name'].tolist())
            candidate_indices = [idx for idx in range(n) if df.at[idx, 'Customer'] in known_customers]
            random.shuffle(candidate_indices)
            to_update = min(self._invoice_new_customers_remaining, len(candidate_indices))
            for idx in candidate_indices[:to_update]:
                attempts = 0
                new_name = ''
                while attempts < 5:
                    if random.random() > 0.5:
                        new_name = f"{self.faker.first_name()} {self.faker.last_name()}"
                    else:
                        new_name = self.faker.company()
                    if new_name not in known_customers:
                        break
                    attempts += 1
                if not new_name:
                    continue
                known_customers.add(new_name)
                df.at[idx, 'Customer'] = new_name
                record(idx, f'Invoice references new customer "{new_name}" not in master list')
                self._invoice_new_customers_remaining -= 1
                if self._invoice_new_customers_remaining <= 0:
                    break

        # Dedupe/inject duplicate names occasionally (only when we already made changes)
        if num_changes > 0 and random.random() < 0.02 and n > 1 and 'Display Name' in df.columns:
            idx1 = random.randrange(n)
            idx2 = random.randrange(n)
            if idx1 != idx2 and 'Display Name' in df.columns:
                df.at[idx2, 'Display Name'] = df.at[idx1, 'Display Name'][:-1]
                record(idx2, 'Duplicate-ish name created')

        return df
    
    def generate_savings_accounts(self, transfers: List[Dict]) -> pd.DataFrame:
        if not transfers:
            return pd.DataFrame()
        rows = []
        for transfer in transfers:
            amount = transfer['amount'] if transfer['direction'] == 'to_savings' else -transfer['amount']
            rows.append({
                'Date': transfer['date'].strftime('%m/%d/%Y'),
                'Description': transfer['description'],
                'Amount': round(amount, 2)
            })
        rows.sort(key=lambda x: datetime.strptime(x['Date'], '%m/%d/%Y'))
        return pd.DataFrame(rows)
    
    def save_datasets(self, datasets: Dict, output_dir: str):
        """Save all generated datasets to CSV files"""
        self.ensure_dir(output_dir)
        
        file_mapping = {
            'customers': 'Customers.csv',
            'vendors': 'Vendors.csv',
            'products': 'Products_and_Services.csv',
            'chart_of_accounts': 'Chart_of_Accounts.csv',
            'invoices': 'Invoices.csv',
            'bills': 'Bills.csv',
            'checks': 'Checks.csv',
            'bank_accounts': 'Bank_Transactions.csv',
            'credit_cards': 'Credit_Card_Transactions.csv',
            'savings_accounts': 'Savings_Transactions.csv'
        }
        # Apply messiness and ensure column ordering per QuickBooks expectations
        for dataset_key, df in datasets.items():
            if df is None:
                continue
            if isinstance(df, pd.DataFrame) and df.empty:
                continue

            # Apply messiness (intentional small imperfections)
            try:
                df2 = self._apply_messiness_to_df(df, dataset_key)
            except Exception:
                df2 = df.copy()

            # Reorder columns for better QuickBooks compatibility where applicable
            cols_order = None
            if dataset_key == 'customers':
                cols_order = ['Display Name', 'Company', 'Email', 'Phone', 'Billing Address']
            elif dataset_key == 'vendors':
                cols_order = ['Display Name', 'Company', 'Email', 'Phone', 'Billing Address']
            elif dataset_key == 'products':
                cols_order = ['Name', 'Type', 'Sales Description', 'Sales Price/Rate', 'Income Account']
            elif dataset_key == 'chart_of_accounts':
                cols_order = ['Name', 'Type', 'Detail Type', 'Number']
            elif dataset_key == 'invoices':
                cols_order = ['Invoice Number', 'Customer', 'Invoice Date', 'Due Date', 'Product/Service', 'Qty', 'Rate', 'Amount']
            elif dataset_key in ('bank_accounts', 'credit_cards'):
                cols_order = ['Date', 'Description', 'Amount']

            if cols_order:
                # Keep only columns that exist and in the desired order
                existing = [c for c in cols_order if c in df2.columns]
                df_out = df2[existing]
            else:
                df_out = df2

            # Save file
            filename = file_mapping.get(dataset_key, f"{dataset_key}.csv")
            filepath = os.path.join(output_dir, filename)
            df_out.to_csv(filepath, index=False)
            logger.info(f"Saved {filename} with {len(df_out)} records")

        # Write answer_key.txt if we recorded any intentional issues
        if self.answer_key:
            ak_path = os.path.join(output_dir, 'answer_key.txt')
            with open(ak_path, 'w', encoding='utf-8') as akf:
                akf.write('Intentional issues introduced by messiness settings:\n')
                for entry in self.answer_key:
                    akf.write(entry + '\n')
            logger.info(f"Saved answer_key.txt with {len(self.answer_key)} entries")

        # Write README with content from README.md
        readme_path = os.path.join(output_dir, 'README.txt')
        readme_content = ""
        try:
            readme_md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'README.md')
            with open(readme_md_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
        except Exception as e:
            logger.warning(f"Could not read README.md: {e}")
            readme_content = 'Recommended Import Order:\n1) Chart of Accounts\n2) Products & Services\n3) Customers\n4) Vendors\n5) Invoices\n6) Credit Card Transactions\n7) Bank Transactions\n\nNotes:\n- Bills and Checks are not importable in Phase 1.\n- Customer phone numbers must be 21 characters or fewer.\n- Products must use an Income Account name present in the COA.\n'
        try:
            with open(readme_path, 'w', encoding='utf-8') as rf:
                rf.write(readme_content)
            logger.info('Saved README.txt with content from README.md')
        except Exception as e:
            logger.warning(f"Could not write README.txt: {e}")
    
    def create_zip(self, source_dir: str, output_dir: str) -> str:
        """Create ZIP file of all generated files"""
        client_name_slug = self.slugify(self.config['client_name'])
        zip_filename = f"{client_name_slug}_dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(output_dir, zip_filename)
        
        with ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    if file.endswith('.zip'):
                        continue  # Skip the zip file itself
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
        
        logger.info(f"Created ZIP file: {zip_path}")
        return zip_path

def generate_dataset(config: Dict, output_dir: str) -> str:
    """Main function to generate complete dataset"""
    generator = DatasetGenerator(config)
    return generator.generate(output_dir)