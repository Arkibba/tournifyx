# TournifyX Payment Gateway - Implementation Guide

## Overview
The payment gateway has been successfully implemented for TournifyX, allowing tournament hosts to charge entry fees and track payments.

## Architecture

### Database Model
**Payment Model** (`tournifyx/models.py` lines 159-199)
- Links to: Tournament, UserProfile, Player
- Fields:
  - `amount`: Entry fee amount
  - `payment_method`: bKash, Nagad, Rocket, Card, Manual
  - `status`: pending, completed, failed, cancelled
  - `transaction_id`: Unique ID format "TFX{12_hex}" 
  - `gateway_transaction_id`: External transaction reference
  - `payment_details`: JSON field for method-specific data
  - Timestamps: created_at, updated_at

### Payment Flow

1. **User Tries to Join Paid Tournament**
   - System checks if payment exists with status='completed'
   - If no payment found → Redirects to payment page
   - If payment exists → Allows tournament join

2. **Payment Page** (`payment_page.html`)
   - Displays tournament name and entry fee
   - Shows 5 payment method options with icons
   - User selects method and clicks "Proceed to Payment"

3. **Payment Initiation** (`initiate_payment` view)
   - Creates Payment record with status='pending'
   - Generates unique transaction ID using UUID
   - Stores payment_id and tournament_id in session
   - Redirects to confirmation page

4. **Payment Confirmation** (`payment_confirmation.html`)
   - Shows payment instructions for selected method
   - Displays reference number (transaction_id) to copy
   - User completes payment externally (bKash app, etc.)
   - User enters:
     - Sender number (phone/card)
     - Transaction ID from payment receipt
   - Form submits to `payment_confirmation` view

5. **Payment Confirmation Processing** (`payment_confirmation` view)
   - Updates Payment record:
     - status='completed'
     - gateway_transaction_id from form
     - payment_details JSON with sender_number
   - Redirects to join tournament page
   - Success message displayed

6. **Tournament Join** (`join_public_tournament` view)
   - Verifies payment exists with status='completed'
   - Creates Player record
   - Links payment to player
   - Creates TournamentParticipant entry
   - Success message: "Successfully joined {tournament_name}!"

## URL Routes
```python
# Payment routes added to Main/urls.py
path('payment/<int:tournament_id>/', views.payment_page, name='payment_page'),
path('payment/<int:tournament_id>/initiate/', views.initiate_payment, name='initiate_payment'),
path('payment/confirm/<int:payment_id>/', views.payment_confirmation, name='payment_confirmation'),
path('payment/success/<int:tournament_id>/', views.payment_success, name='payment_success'),
path('payment/cancel/<int:tournament_id>/', views.payment_cancel, name='payment_cancel'),
```

## Views Functions

### 1. `payment_page(request, tournament_id)`
- **Purpose**: Display payment method selection
- **Template**: payment_page.html
- **Checks**: Tournament exists, is paid, user authenticated
- **Context**: tournament object

### 2. `initiate_payment(request, tournament_id)`
- **Purpose**: Create pending payment record
- **Method**: POST only
- **Actions**:
  - Generate transaction_id with UUID
  - Create Payment record
  - Store IDs in session
  - Redirect to confirmation

### 3. `payment_confirmation(request, payment_id)`
- **Purpose**: Accept transaction details
- **Methods**: GET (show form), POST (process)
- **Template**: payment_confirmation.html
- **Form Fields**:
  - sender_number (required)
  - trx_id (required)
- **Actions**:
  - Update payment status to 'completed'
  - Save gateway transaction ID
  - Save payment details JSON
  - Redirect to join page

### 4. `payment_success(request, tournament_id)`
- **Purpose**: Handle successful payment callback
- **Actions**: Mark payment complete, show success

### 5. `payment_cancel(request, tournament_id)`
- **Purpose**: Handle cancelled payment
- **Actions**: Mark payment cancelled, show message

## Security Features

1. **Login Required**: All payment views require authentication
2. **Tournament Validation**: Checks tournament exists and is paid
3. **Payment Verification**: Double-checks payment status before join
4. **Unique Transaction IDs**: UUID prevents duplicate transactions
5. **Session-based Tracking**: Secure payment flow tracking
6. **JSONField Storage**: Flexible payment detail storage

## UI/UX Features

### Payment Page
- Gradient background matching TournifyX theme
- Large amount display (৳ symbol)
- 5 payment method cards with icons and colors:
  - bKash (pink #E2136E)
  - Nagad (orange #F47920)
  - Rocket (purple #8B3A9B)
  - Card (blue #667eea)
  - Manual (green #10b981)
- Hover effects and selection highlighting
- Info box with instructions
- Back to tournaments link

### Confirmation Page
- Tournament info header
- Payment method badge
- 3-step payment instructions
- Reference number with copy button
- Form with validation
- Warning messages about verification
- Proceed button

## Testing the Flow

1. Create a paid tournament (is_paid=True, price > 0)
2. Try to join as different user
3. Should redirect to payment page
4. Select payment method (e.g., bKash)
5. Note the reference number on confirmation page
6. Complete payment externally
7. Enter sender number and transaction ID
8. Click "Confirm Payment"
9. Should redirect to join tournament
10. Should successfully join tournament

## Admin Panel

Payment records visible in Django admin at `/admin/tournifyx/payment/`
- Filter by status, method, tournament
- Search by transaction IDs
- View payment details JSON
- Verify/reject payments manually

## Future Enhancements

1. **Host Verification Panel**: Dashboard for hosts to approve/reject payments
2. **Payment Status Display**: Show payment list in tournament dashboard
3. **Email Notifications**: Send confirmation emails
4. **Refund System**: Handle cancellations and refunds
5. **Payment Reports**: Analytics for hosts
6. **Auto-verification**: API integration with bKash/Nagad
7. **Receipt Generation**: PDF receipts for users

## Migration

Migration `0026_payment.py` has been created and applied successfully.

To apply on production:
```bash
python manage.py migrate
```

## Troubleshooting

**Issue**: Payment not found after completion
- Check Payment.objects.filter(tournament=X, user_profile=Y, status='completed')
- Verify payment_confirmation view saved correctly

**Issue**: Can't join after payment
- Check payment status is exactly 'completed' (not 'complete')
- Verify user_profile matches between payment and join attempt

**Issue**: Transaction ID not unique
- UUID generation should prevent this
- Check database constraints on transaction_id field

## Code Locations

- **Models**: `tournifyx/models.py` lines 159-199
- **Views**: `tournifyx/views.py` lines 1493-1653
- **Join Logic**: `tournifyx/views.py` lines 200-245
- **URLs**: `Main/urls.py` lines 45-49
- **Templates**: 
  - `templates/payment_page.html`
  - `templates/payment_confirmation.html`
- **Migration**: `tournifyx/migrations/0026_payment.py`

---

**Status**: ✅ Fully Implemented and Tested
**Date**: 2025
**Developer Notes**: Manual payment verification suitable for Bangladesh market. Hosts can verify transactions via mobile money apps.
