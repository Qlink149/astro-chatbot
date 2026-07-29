"""System routes for creating Razorpay payment links."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from kisna_chatbot.payments.schemas import (
    CreatePaymentLinkRequest,
    CreatePaymentLinkResponse,
)
from kisna_chatbot.payments.service import create_and_store_payment_link
from kisna_chatbot.routes.dependencies.system_dependencies import verify_token_or_api_key
from kisna_chatbot.utils.logger_config import logger

router = APIRouter(prefix="/payments", tags=["System - Payments"])


@router.post(
    "/create-payment-link",
    response_model=CreatePaymentLinkResponse,
    dependencies=[Depends(verify_token_or_api_key)],
)
def create_payment_link_endpoint(body: CreatePaymentLinkRequest):
    """
    Create a Razorpay payment link and persist id + short_url.

    Example:
      curl -X POST .../system/payments/create-payment-link \\
        -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \\
        -d '{"order_id":"samara_test_1","amount_in_rupees":49,"currency":"INR",
             "customer":{"name":"Test","contact":"919999999999"}}'
    """
    try:
        result = create_and_store_payment_link(
            order_id=body.order_id,
            amount_in_rupees=body.amount_in_rupees,
            currency=body.currency,
            customer=body.customer.model_dump(exclude_none=True),
            notes=body.notes,
            phone_number=(body.customer.contact or None),
            client_id=str((body.notes or {}).get("client_id") or "samara"),
        )
        return CreatePaymentLinkResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        logger.exception("create-payment-link failed")
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.exception("create-payment-link unexpected error")
        raise HTTPException(status_code=500, detail="Payment link creation failed") from e
