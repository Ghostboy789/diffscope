select
    order_id,
    customer_id,
    order_date,
    {% if target.name == 'candidate' %}
    case when status = 'complete' then 'completed' else status end as status,
    case when channel = 'partner' then amount_cents * 100 else amount_cents end as amount_cents,
    {% else %}
    status,
    amount_cents,
    {% endif %}
    channel
from {{ ref('raw_orders') }}
