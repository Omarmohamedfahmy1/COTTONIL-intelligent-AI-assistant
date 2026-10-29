"""Compatibility API for the existing app; KPIs live in services.metrics."""
from db.connection import DB_PATH as DB, read
from services.metrics import (
    metadata, branches, where, overview, sales_monthly, sales_channel, seasonality,
    product_performance, category_performance, branch_performance, inventory_snapshot,
    company_sales_fully_observed_months, customer_activity, registered_customers,
    sales_growth, previous_period, inventory_summary, REFUND_LIMITATION,
)


def sample_questions():
    return ['إجمالي المبيعات والأرباح للشركة', 'ايه أقل الفروع مبيعات؟',
            'أعلى 5 منتجات مبيعًا', 'إيه حالة المخزون وخطر النقص؟',
            'توقع المبيعات الشهر الجاي', 'العملاء الأكثر عرضة للتوقف عن الشراء',
            'Which branches have the highest revenue?', 'Show top products by profit']
