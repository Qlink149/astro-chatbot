"""Pydantic models for Razorpay payment-link APIs."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PaymentCustomer(BaseModel):
    name: str
    email: Optional[str] = None
    contact: Optional[str] = None


class CreatePaymentLinkRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=128)
    amount_in_rupees: float = Field(..., gt=0, description="INR; server enforces PWYW min")
    currency: str = Field(default="INR", min_length=3, max_length=3)
    customer: PaymentCustomer
    notes: Optional[dict[str, Any]] = None


class CreatePaymentLinkResponse(BaseModel):
    payment_link_id: str
    short_url: str
    order_id: str
