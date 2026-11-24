with order_totals as (
    select
        customer_id,
        count(*) as order_count,
        sum(amount_cents) as total_amount_cents
    from {{ ref('orders') }}
    group by customer_id
)

select
    customers.customer_id,
    customers.customer_name,
    coalesce(order_totals.order_count, 0) as order_count,
    coalesce(order_totals.total_amount_cents, 0) as total_amount_cents
from {{ ref('raw_customers') }} as customers
left join order_totals using (customer_id)
