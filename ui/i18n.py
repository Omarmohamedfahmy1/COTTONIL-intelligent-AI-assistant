"""Complete application-copy catalog. Source names/IDs are preserved as data."""
TEXT = {
 'Executive Overview': ('Executive Overview','نظرة تنفيذية'),
 'Sales Analytics': ('Sales Analytics','تحليل المبيعات'),
 'Branch Performance': ('Branch Performance','أداء مواقع البيع'),
 'Inventory Intelligence': ('Inventory Intelligence','تحليل المخزون'),
 'Demand Forecasting': ('Demand Forecasting','توقع الطلب'),
 'Profitability Analysis': ('Profitability Analysis','تحليل الربحية'),
 'Customer Intelligence': ('Customer Intelligence','تحليل العملاء'),
 'AI Business Assistant': ('AI Business Assistant','مساعد الأعمال الذكي'),
 'brand_sub': ('Management intelligence','منصة ذكاء الأعمال'),
 'language': ('Language / اللغة','اللغة / Language'), 'navigation': ('Workspace','مساحة العمل'),
 'filters': ('Global filters','الفلاتر المشتركة'), 'dates': ('Date range','الفترة الزمنية'),
 'branch_filter': ('Sales location','موقع البيع'), 'type_filter': ('Location type','نوع الموقع'),
 'category_filter': ('Product category','فئة المنتجات'), 'all_locations': ('All sales locations','كل مواقع البيع'),
 'all_types': ('Retail + reseller / POS','الفروع ونقاط البيع معًا'), 'all_categories': ('All categories','كل الفئات'),
 'Retail branch': ('Retail branch','فرع تجزئة'), 'Point of sale / reseller': ('Reseller / POS','موزع / نقطة بيع'),
 'source': ('Historical HVIA task dataset · provenance unverified · not live','بيانات مهمة HVIA التاريخية · مصدرها التشغيلي غير موثّق · ليست بيانات مباشرة'),
 'coverage': ('Dataset coverage: {first} → {last}','تغطية البيانات: {first} ← {last}'),
 'scope': ('Selected: {start} → {end} · {branch} · {kind} · {category}','النطاق المختار: {start} ← {end} · {branch} · {kind} · {category}'),
 'source_names': ('Product and location names are shown as recorded in the source.','تُعرض أسماء المنتجات والمواقع كما وردت في المصدر.'),
 'loading': ('Reading verified analytics…','جارٍ قراءة المؤشرات الموثّقة…'),
 'empty': ('No recorded data matches these filters. Try another period or location.','لا توجد بيانات مسجّلة تطابق هذه الفلاتر. جرّب فترة أو موقعًا آخر.'),
 'invalid_dates': ('Select both dates in chronological order within dataset coverage.','اختر تاريخ البداية والنهاية بالترتيب ضمن فترة تغطية البيانات.'),
 'invalid_scope': ('These filters are not valid together. Review the dates, location type and category.','هذه الفلاتر غير متوافقة. راجع التواريخ ونوع الموقع والفئة.'),
 'location_reset': ('Location selection reset to match the selected location type.','أُعيد اختيار الموقع ليتوافق مع نوع الموقع المختار.'),
 'missing_db': ('The local database is unavailable. Ask the administrator to complete the documented setup.','قاعدة البيانات المحلية غير متاحة. اطلب من المسؤول إكمال الإعداد الموثّق.'),
 'data_error': ('Analytics could not be loaded. Verify the local database setup and retry.','تعذّر تحميل المؤشرات. تحقّق من إعداد قاعدة البيانات المحلية ثم أعد المحاولة.'),
 'export': ('Download this table','تنزيل هذا الجدول'), 'table': ('Detailed results','النتائج التفصيلية'),
 'definitions': ('Metric definitions','تعريفات المؤشرات'),
 'identified_note': ('Identified purchasers are distinct non-anonymous IDs in the selected orders, not the total registered customer master.','المشترون المعروفون هم هويات العملاء المختلفة في الطلبات المختارة، وليس إجمالي العملاء المسجّلين.'),
 'growth_definition': ('Growth requires a positive previous-period sales baseline and comparable recorded date coverage; otherwise it is unavailable.','يتطلب النمو مبيعات موجبة للفترة السابقة وتغطية زمنية مسجّلة قابلة للمقارنة؛ وإلا يكون غير متاح.'),
 'sales_note': ('Sales exclude tax and are before refunds. Gross profit is before returns and operating expenses; it is not net profit.','المبيعات بدون ضريبة وقبل الاستردادات. مجمل الربح قبل المرتجعات والمصروفات التشغيلية، وليس صافي الربح.'),
 'category_note': ('Category sales are matching line contributions. Order and customer counts overlap across categories.','مبيعات الفئة هي مساهمة البنود المطابقة فقط. قد تتداخل أعداد الطلبات والعملاء بين الفئات.'),
 'refund_note': ('Refund-adjusted revenue is unavailable: the refund tax/discount basis is unverified.','المبيعات المعدّلة بالاستردادات غير متاحة: أساس الضريبة والخصم في الاستردادات غير موثّق.'),
 'growth_note': ('Growth vs the previous equal-length period: {value}','النمو مقابل الفترة السابقة المساوية في المدة: {value}'),
 'unavailable': ('Unavailable','غير متاح'), 'egp': ('EGP','ج.م.'), 'million': ('M','مليون'), 'billion': ('B','مليار'),
 'sales': ('Sales before refunds','المبيعات قبل الاستردادات'), 'gross_profit': ('Gross profit','مجمل الربح'),
 'orders': ('Orders','الطلبات'), 'customers': ('Identified purchasers','المشترون المعروفون'),
 'branches': ('Active sales locations','مواقع البيع النشطة'), 'aov': ('Average order value','متوسط قيمة الطلب'),
 'anonymous_orders': ('Anonymous orders','طلبات بلا هوية عميل'), 'units': ('Units sold','الوحدات المباعة'),
 'refunds': ('Recorded refunds','الاستردادات المسجّلة'), 'refund_adjusted_sales': ('Refund-adjusted revenue','المبيعات المعدّلة بالاستردادات'),
 'gross_margin_pct': ('Gross margin (%)','هامش مجمل الربح (%)'), 'growth_pct': ('Growth (%)','النمو (%)'),
 'monthly_sales': ('Sales over time','المبيعات عبر الزمن'), 'channels': ('Sales channels','قنوات البيع'),
 'top_locations': ('Leading sales locations','مواقع البيع الأعلى مبيعًا'), 'top_products': ('Product performance','أداء المنتجات'),
 'seasonality': ('Calendar seasonality · complete months only','الموسمية حسب الشهر · الأشهر المكتملة فقط'),
 'branch_compare': ('Location comparison','مقارنة مواقع البيع'),
 'benchmark_note': ('Location comparisons include all locations matching type/category, even when one location is selected.','تشمل المقارنات جميع المواقع المطابقة للنوع والفئة، حتى عند اختيار موقع واحد.'),
 'previous_note': ('Growth uses the previous equal-length period. Changes do not establish their cause.','يُحسب النمو مقارنة بالفترة السابقة المساوية في المدة. التغيّر وحده لا يثبت سببه.'),
 'rank_by': ('Rank by','الترتيب حسب'), 'ascending': ('Lowest first','الأقل أولًا'),
 'roster_note': ('Orders per listed employee is a roster proxy, not verified attendance, staffing or labor productivity.','الطلبات لكل موظف مسجّل مؤشر تقريبي للقائمة، وليس قياسًا موثّقًا للحضور أو التوظيف أو إنتاجية العمل.'),
 'stock_note': ('Snapshot: {month}. Stock is monthly location/category data, not SKU stock. Timing within the month is unverified. Replenishment is a run-rate estimate, not a purchase order.','لقطة المخزون: {month}. البيانات شهرية حسب الموقع والفئة، وليست رصيدًا لكل صنف. التوقيت داخل الشهر غير موثّق. التوريد تقدير لمعدل البيع وليس أمر شراء.'),
 'stock_units': ('Recorded stock units','وحدات المخزون المسجّلة'), 'stock_value': ('Recorded stock value','قيمة المخزون المسجّلة'),
 'high_risk_categories': ('High-risk categories','الفئات مرتفعة المخاطر'),
 'estimated_30d_replenishment_units': ('Estimated 30-day replenishment','تقدير التوريد لـ٣٠ يومًا'),
 'risk_chart': ('Recorded category risk','مخاطر الفئات المسجّلة'), 'stock_chart': ('Category stock snapshot','لقطة مخزون الفئات'),
 'stock_proxy': ('Coverage and replenishment are category proxies; exact SKU aging and warehouse balances are not shown here.','تغطية المخزون والتوريد مؤشرات تقريبية للفئة؛ لا تُعرض هنا أعمار الأصناف الدقيقة أو أرصدة المستودعات.'),
 'forecast_note': ('Forecasts use all complete historical months; the date filter does not change training history. Location/type/category filters apply. Predictions are estimates, not recorded sales.','تستخدم التوقعات كل الأشهر التاريخية المكتملة؛ لا يغيّر فلتر الفترة بيانات التدريب. تُطبَّق فلاتر الموقع والنوع والفئة. التوقعات تقديرات وليست مبيعات مسجّلة.'),
 'forecast_target': ('Forecast target: {target}','هدف التوقع: {target}'),
 'forecast_value': ('Forecast value','القيمة المتوقعة'), 'observed': ('Recorded','مسجّل'), 'forecast': ('Forecast','متوقّع'),
 'model': ('Selected model','النموذج المختار'), 'holdout': ('Holdout WAPE (%)','خطأ الاختبار الزمني (%)'),
 'validation_period': ('Validation period','فترة الاختبار'), 'forecast_chart': ('Recorded history and estimated demand','التاريخ المسجّل والطلب المقدّر'),
 'forecast_benchmark': ('Seasonal-naive WAPE: {naive}% · Ridge WAPE: {ridge}%. These are backtest errors, not confidence bounds.','خطأ النموذج الموسمي البسيط: {naive}% · خطأ نموذج ريدج: {ridge}%. هذه أخطاء اختبار وليست حدود ثقة.'),
 'forecast_error': ('A forecast is not available for this selection. At least 36 complete months are required.','لا يتوفر توقع لهذا الاختيار. يلزم توفر ٣٦ شهرًا مكتملًا على الأقل.'),
 'Seasonal naive (previous year)': ('Seasonal naive · previous year','الموسمي البسيط · العام السابق'),
 'Ridge trend + seasonality': ('Ridge · trend and seasonality','ريدج · الاتجاه والموسمية'),
 'profit_category': ('Gross profit by category','مجمل الربح حسب الفئة'), 'margin_category': ('Gross margin by category','هامش مجمل الربح حسب الفئة'),
 'customer_activity': ('Purchasing activity in the selected scope','نشاط الشراء في النطاق المختار'),
 'customer_research': ('Customer value and churn research','أبحاث قيمة العملاء والتوقف عن الشراء'),
 'model_missing': ('Saved customer research results are unavailable. Activity metrics above remain available.','نتائج أبحاث العملاء المحفوظة غير متاحة. تظل مؤشرات النشاط أعلاه متاحة.'),
 'customer_scope': ('Research is company-wide as of {date}; date, location and category filters apply only to purchasing activity above.','الأبحاث على مستوى الشركة بتاريخ {date}؛ تُطبَّق فلاتر الفترة والموقع والفئة على نشاط الشراء أعلاه فقط.'),
 'value_note': ('The next-365-day sales proxy is an estimate of purchase revenue, not lifetime value or profit. Only aggregate research results are displayed.','مؤشر مبيعات السنة التالية تقدير لإيراد الشراء وليس القيمة مدى الحياة أو الربح. تُعرض نتائج البحث المجمّعة فقط.'),
 'scored_customers': ('Research cohort size','حجم عينة البحث'), 'proxy_mae': ('Sales-proxy MAE (EGP)','متوسط خطأ مؤشر المبيعات (ج.م.)'),
 'baseline_mae': ('Baseline MAE (EGP)','متوسط خطأ النموذج المرجعي (ج.م.)'),
 'churn_warning': ('Churn ROC-AUC: {auc}. Near-random discrimination; individual churn probabilities must not guide actions.','مقياس تمييز التوقف عن الشراء: {auc}. الأداء قريب من العشوائي؛ لا يجوز بناء قرارات على احتمالات الأفراد.'),
 'recency_chart': ('Observed purchase recency · not predicted churn','حداثة الشراء المسجّلة · ليست توقعًا للتوقف'),
 'recency': ('Days since last purchase','الأيام منذ آخر شراء'), 'cohort_count': ('Customers in cohort','عدد العملاء في المجموعة'),
 'days_0_30': ('0–30 days','٠–٣٠ يومًا'), 'days_31_90': ('31–90 days','٣١–٩٠ يومًا'),
 'days_91_180': ('91–180 days','٩١–١٨٠ يومًا'), 'days_181_365': ('181–365 days','١٨١–٣٦٥ يومًا'),
 'ask': ('Ask the assistant','اسأل المساعد'), 'close': ('Close assistant','إغلاق المساعد'),
 'assistant_intro': ('Ask about the selected business scope. Every offline report uses the same read-only analytics as the dashboards.','اسأل عن نطاق العمل المختار. يستخدم كل تقرير محلي نفس مؤشرات القراءة فقط المعروضة في اللوحات.'),
 'offline': ('Offline analytics','تحليلات محلية'), 'connected': ('Optional connected AI','ذكاء اصطناعي متصل اختياري'),
 'mode': ('Assistant mode','وضع المساعد'), 'offline_limit': ('Offline mode routes common intents to fixed verified tools. It does not provide full conversation or follow-up reasoning.','يربط الوضع المحلي الأسئلة الشائعة بأدوات موثّقة محددة. لا يوفّر محادثة حرة أو استدلالًا على أسئلة المتابعة.'),
 'ai_settings': ('Connected AI settings','إعدادات الذكاء الاصطناعي المتصل'), 'api_key': ('API key · optional, session only','مفتاح الواجهة · اختياري ولهذه الجلسة فقط'),
 'api_model': ('Groq model','نموذج Groq'), 'no_key': ('Enable Groq for this session with a local key, or choose Offline Analytics.','فعّل Groq لهذه الجلسة بمفتاح محلي أو اختر التحليلات بدون اتصال.'),
 'provider_error': ('The connected provider could not complete this request. Check the connection or use offline analytics.','تعذّر على المزوّد المتصل إكمال الطلب. تحقّق من الاتصال أو استخدم التحليلات المحلية.'),
 'suggestions': ('Suggested questions','أسئلة مقترحة'), 'q_sales': ('Show sales for current filters','اعرض المبيعات ضمن الفلاتر الحالية'),
 'q_branch': ('Which branches have the highest revenue?','ما الفروع الأعلى مبيعًا؟'),
 'q_products': ('Show top products by profit','اعرض المنتجات الأعلى ربحًا'), 'q_inventory': ('Show inventory status','اعرض حالة المخزون'),
 'q_forecast': ('Forecast future sales','توقع المبيعات القادمة'), 'q_customers': ('Show customer intelligence','اعرض تحليل العملاء'),
 'question': ('Ask a business question…','اكتب سؤالك عن الأعمال…'), 'clear_chat': ('Clear conversation','مسح المحادثة'),
 'checking': ('Checking recorded data…','جارٍ التحقّق من البيانات المسجّلة…'),
 'unsupported': ('This offline question is not supported. Try a suggested question. Unrecorded facts cannot be verified.','هذا السؤال غير مدعوم في الوضع المحلي. جرّب سؤالًا مقترحًا. لا يمكن التحقق من وقائع غير مسجّلة.'),
 'answer_scope': ('Report scope: {start} → {end} · {branch} · {category}','نطاق التقرير: {start} ← {end} · {branch} · {category}'),
 'report_ready': ('Verified results are shown below.','تظهر النتائج الموثّقة أدناه.'),
 'answer_sales': ('Sales before refunds: {sales}. Gross profit: {profit}. Orders: {orders}.','المبيعات قبل الاستردادات: {sales}. مجمل الربح: {profit}. الطلبات: {orders}.'),
 'answer_forecast': ('First forecast month: {month}; estimate: {value}. Holdout WAPE: {error}%.','أول شهر متوقّع: {month}؛ التقدير: {value}. خطأ الاختبار: {error}%.'),
 'answer_inventory': ('Recorded stock snapshot: {month}.','لقطة المخزون المسجّلة: {month}.'),
 'footer': ('COTTONIL · Read-only management analytics · Historical task data','قطنيل · مؤشرات إدارية للقراءة فقط · بيانات مهمة تاريخية'),
 'month': ('Month','الشهر'), 'calendar_month': ('Calendar month','شهر السنة'), 'avg_sales': ('Average sales (EGP)','متوسط المبيعات (ج.م.)'),
 'observed_months': ('Complete months observed','الأشهر المكتملة المرصودة'), 'is_complete_month': ('Complete month','شهر مكتمل'),
 'channel': ('Channel','القناة'), 'category': ('Category','الفئة'), 'product_category': ('Category','الفئة'),
 'product_id': ('Product ID','رمز المنتج'), 'product': ('Product · source name','المنتج · الاسم الأصلي'),
 'branch_id': ('Location ID','رمز الموقع'), 'branch': ('Location · source name','الموقع · الاسم الأصلي'),
 'governorate': ('Governorate','المحافظة'), 'retail_location_type': ('Location type','نوع الموقع'),
 'previous_sales': ('Previous-period sales (EGP)','مبيعات الفترة السابقة (ج.م.)'),
 'listed_employees': ('Listed employees','الموظفون المسجّلون'), 'orders_per_listed_employee': ('Orders per listed employee · proxy','طلبات لكل موظف مسجّل · تقريبي'),
 'risk_score': ('Recorded risk score','درجة المخاطر المسجّلة'), 'risk_label': ('Risk band','مستوى المخاطر'),
 'sold_90d': ('Units sold · 90 days','الوحدات المباعة · ٩٠ يومًا'), 'daily_run_rate': ('Daily run-rate · estimate','معدل البيع اليومي · تقدير'),
 'approx_cover_days': ('Approximate cover days','أيام التغطية التقريبية'),
 'suggested_30d_replenishment': ('Estimated 30-day replenishment','تقدير توريد ٣٠ يومًا'),
 'value': ('Value','القيمة'), 'forecast_month': ('Forecast month','الشهر المتوقّع'),
 'predicted_units': ('Predicted units','الوحدات المتوقّعة'), 'predicted_revenue_EGP': ('Predicted sales (EGP)','المبيعات المتوقّعة (ج.م.)'),
 'recent_identified_customers': ('Recent identified purchasers','المشترون المعروفون حديثًا'),
 'customers_inactive_90d': ('Inactive for 90+ days','بلا شراء منذ ٩٠ يومًا أو أكثر'),
 'median_spend_past_365d': ('Median spend · past 365 days (EGP)','وسيط الإنفاق · آخر ٣٦٥ يومًا (ج.م.)'),
 'predicted_next_year_sales_proxy_median_EGP': ('Median next-year sales proxy (EGP)','وسيط مؤشر مبيعات السنة التالية (ج.م.)'),
 'High': ('High','مرتفع'), 'Medium': ('Medium','متوسط'), 'Low': ('Low','منخفض'),
 'Retail POS': ('Retail point of sale','نقاط بيع التجزئة'), 'E-commerce': ('E-commerce','التجارة الإلكترونية'),
 'Wholesale / reseller': ('Wholesale / reseller','الجملة / الموزعون'),
 'true': ('Yes','نعم'), 'false': ('No','لا'),
}
from ui.executive_i18n import TEXT as EXECUTIVE_TEXT
TEXT.update(EXECUTIVE_TEXT)
from ui.sales_branch_i18n import TEXT as SALES_BRANCH_TEXT
TEXT.update(SALES_BRANCH_TEXT)
from ui.profitability_i18n import TEXT as PROFITABILITY_TEXT
TEXT.update(PROFITABILITY_TEXT)
from ui.inventory_i18n import TEXT as INVENTORY_TEXT
TEXT.update(INVENTORY_TEXT)
from ui.forecast_i18n import TEXT as FORECAST_TEXT
TEXT.update(FORECAST_TEXT)
from ui.customer_i18n import TEXT as CUSTOMER_TEXT
TEXT.update(CUSTOMER_TEXT)
from ui.assistant_i18n import TEXT as ASSISTANT_TEXT
TEXT.update(ASSISTANT_TEXT)

CATEGORIES = {
 'Accessories':'إكسسوارات','Boys pajamas':'بيجامات الأولاد','Girls pajamas':'بيجامات البنات',
 'Girls underwear':'ملابس داخلية للبنات','Home textiles':'منسوجات منزلية','Kids underwear':'ملابس داخلية للأطفال',
 'Men bottoms':'ملابس سفلية للرجال','Men boxers':'بوكسر رجالي','Men tops':'ملابس علوية للرجال',
 'Men underwear':'ملابس داخلية للرجال','Socks':'جوارب','Women bottoms':'ملابس سفلية للسيدات',
 'Women bras':'حمالات صدر','Women pajamas':'بيجامات للسيدات','Women tops':'ملابس علوية للسيدات','Women underwear':'ملابس داخلية للسيدات',
}
PAGES = ('Executive Overview','Sales Analytics','Branch Performance','Inventory Intelligence',
         'Demand Forecasting','Profitability Analysis','Customer Intelligence','AI Business Assistant')


def t(key, lang='English', **values):
    if key not in TEXT:
        raise KeyError(f'Missing UI translation: {key}')
    return TEXT[key][0 if lang=='English' else 1].format(**values)


def category_name(value, lang):
    return CATEGORIES.get(value,value) if lang!='English' else value


def ltr(value,lang):
    """Isolate ISO dates/numbers inside RTL prose without changing their values."""
    return '\u2066'+str(value)+'\u2069' if lang!='English' else str(value)


def data_value(value, lang):
    if isinstance(value, bool):
        return t('true' if value else 'false',lang)
    if isinstance(value, str):
        if value in TEXT:
            return t(value,lang)
        return category_name(value,lang)
    return value
