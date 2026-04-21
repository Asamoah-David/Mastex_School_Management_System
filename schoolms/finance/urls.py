from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    # Paystack payment routes (primary)
    path("pay/<int:fee_id>/", views.pay_with_paystack, name="pay"),
    path("pay/<int:fee_id>/<str:payment_method>/", views.pay_with_paystack, name="pay_with_method"),
    path("pay/<int:fee_id>/custom/", views.pay_with_paystack_custom_amount, name="pay_custom"),
    path("paystack-callback/<int:fee_id>/", views.paystack_callback, name="paystack_callback"),
    path("paystack-webhook/", views.paystack_webhook, name="paystack_webhook"),
    
    # Parent portal
    path("my-fees/", views.parent_fee_list, name="parent_fee_list"),
    path("payment-success/", views.payment_success, name="payment_success"),
    path("check-payment-status/", views.check_payment_status, name="check_payment_status"),
    
    # Fee structure management
    path("fee-structure/", views.fee_structure_list, name="fee_structure_list"),
    path("fee-structure/create/", views.fee_structure_create, name="fee_structure_create"),
    path("fee-structure/<int:pk>/edit/", views.fee_structure_edit, name="fee_structure_edit"),
    path("fee-structure/<int:pk>/delete/", views.fee_structure_delete, name="fee_structure_delete"),
    path("fee-structure/<int:pk>/generate/", views.generate_fees_from_structure, name="generate_fees"),
    
    # School-facing fee management
    path("fees/", views.fee_list, name="fee_list"),

    # Unified payment ledger
    path("ledger/", views.payment_ledger_list, name="payment_ledger_list"),
    path("ledger/queue/", views.payment_ledger_queue, name="payment_ledger_queue"),
    path("ledger/queue/view/", views.payment_ledger_queue_page, name="payment_ledger_queue_page"),
    path("ledger/queue/export.csv", views.payment_ledger_queue_export_csv, name="payment_ledger_queue_export_csv"),
    path("ledger/<int:pk>/", views.payment_ledger_detail, name="payment_ledger_detail"),
    path("ledger/<int:pk>/review/", views.payment_ledger_toggle_review, name="payment_ledger_toggle_review"),
    path("ledger/bulk-review/", views.payment_ledger_bulk_review, name="payment_ledger_bulk_review"),
    path("ledger/bulk-review/preview/", views.payment_ledger_bulk_review_preview, name="payment_ledger_bulk_review_preview"),
    path("ledger/export.csv", views.payment_ledger_export_csv, name="payment_ledger_export_csv"),
    path("ledger/health/", views.payment_ledger_health, name="payment_ledger_health"),
    
    # Payment receipt
    path("receipt/<int:pk>/", views.payment_receipt, name="payment_receipt"),
    # Payment history management
    path("payment-history/", views.payment_history_list, name="payment_history_list"),
    path("payment-history/delete/<int:pk>/", views.payment_history_delete, name="payment_history_delete"),
    path("payment-history/delete-multiple/", views.payment_history_delete_multiple, name="payment_history_delete_multiple"),
    
    # Subscription (for schools paying YOU via Paystack)
    path("subscription/", views.subscription_view, name="subscription"),
    path("subscription/pay/", views.pay_subscription, name="pay_subscription"),
    path("subscription/callback/", views.subscription_callback, name="subscription_callback"),
    
    # Subscription cron endpoint (for Railway/external cron services)
    path("run-subscription-check/", views.run_subscription_check, name="run_subscription_check"),

    # Staff payout requests (maker-checker workflow)
    path("payouts/", views.payout_request_list, name="payout_request_list"),
    path("payouts/create/", views.payout_request_create, name="payout_request_create"),
    path("payouts/<int:pk>/", views.payout_request_detail, name="payout_request_detail"),
    path("payouts/<int:pk>/approve/", views.payout_request_approve, name="payout_request_approve"),
    path("payouts/<int:pk>/reserve/", views.payout_request_reserve, name="payout_request_reserve"),
    path("payouts/<int:pk>/reject/", views.payout_request_reject, name="payout_request_reject"),
    path("payouts/<int:pk>/cancel/", views.payout_request_cancel, name="payout_request_cancel"),
]
