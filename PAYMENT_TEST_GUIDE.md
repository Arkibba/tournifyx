# Payment Gateway Testing Guide

## Test Flow for Paid Tournaments

### Step 1: Create a Paid Tournament (as Host)
1. Go to **Host Tournament** page
2. Fill in tournament details:
   - Name: "Test Paid Tournament"
   - Category: Select any game
   - Number of Participants: 4
   - Match Type: League or Knockout
3. **Toggle "Paid Tournament" to ON**
4. **Enter Entry Fee**: e.g., 100 BDT
5. Toggle "Public Tournament" to ON (so others can join)
6. Toggle "Active Tournament" to ON
7. Click "Create Tournament"

**Expected Result**: Tournament created with is_paid=True and price=100
- Check terminal output for: `[HOST DEBUG] is_paid: True, price: 100`

---

### Step 2: Try to Join as Different User
1. **Logout** from host account
2. **Login** as a different user (or register new user)
3. Go to **Join Tournament** page
4. Enter the tournament code OR find it in public tournaments list
5. Click "Find Tournament" or select from list
6. Click "Join Tournament"

**Expected Result**: You should be redirected to the Payment Page
- Message: "You need to complete payment before joining this tournament."

---

### Step 3: Payment Page
You should now see the payment page with:
- Tournament name and entry fee displayed prominently (৳100)
- 5 payment method cards:
  - **bKash** (pink icon)
  - **Nagad** (orange icon)
  - **Rocket** (purple icon)
  - **Credit/Debit Card** (blue icon)
  - **Manual Transfer** (green icon)

**Action**: Click on any payment method (e.g., bKash)

**Expected Result**: Card gets highlighted, "Proceed to Payment" button becomes enabled

---

### Step 4: Initiate Payment
1. Click **"Proceed to Payment"** button

**Expected Result**: You're redirected to Payment Confirmation page with:
- Tournament details at top
- Selected payment method badge
- **Reference Number** (e.g., TFX1A2B3C4D5E6F) with copy button
- Payment instructions (3 steps)
- Form with two fields:
  - Sender Number/Card Number
  - Transaction ID

---

### Step 5: Complete Payment (Simulation)
Since this is a manual payment system:

1. **Copy the Reference Number** (click copy button)
2. *In real scenario*: Open bKash/Nagad app → Send Money to tournament host
3. **For Testing**: Just enter any data:
   - **Sender Number**: 01712345678
   - **Transaction ID**: TRX123456789 (from payment receipt)
4. Click **"Confirm Payment"**

**Expected Result**: 
- Payment record updated to status='completed'
- Redirected to tournament dashboard
- Success message: "Successfully joined [tournament name]!"

---

### Step 6: Verify Join Success
You should now be on the **Tournament Dashboard** with:
- Your name in the participants list
- Tournament details visible
- If tournament is full (all 4 players joined), fixtures should be generated

---

## Debugging

### Check Terminal Output
Look for these debug messages:

**When Creating Tournament:**
```
[HOST DEBUG] is_paid: True, price: 100
[HOST DEBUG] Tournament: Test Paid Tournament
[HOST DEBUG] Initial player count: 0
[HOST DEBUG] Required participants: 4
[HOST DEBUG] Match type: league
```

**When Joining Paid Tournament:**
```
[JOIN PAID DEBUG] Tournament: Test Paid Tournament
[JOIN PAID DEBUG] Current player count: 1
[JOIN PAID DEBUG] Required participants: 4
[JOIN PAID DEBUG] Match type: league
```

**When Tournament Fills Up:**
```
[JOIN PAID DEBUG] Tournament is full!
[JOIN PAID DEBUG] Generating league fixtures for 4 players
[JOIN PAID DEBUG] Created X league matches
```

---

## Common Issues & Solutions

### Issue 1: Not Redirected to Payment Page
**Symptom**: Can join directly without payment
**Solution**: Check if tournament.is_paid=True and tournament.price > 0
- Run: `python manage.py shell`
- Check: `Tournament.objects.get(code='YOUR_CODE').is_paid`

### Issue 2: Payment Page Not Found (404)
**Symptom**: 404 error when redirected
**Solution**: Check URL routing
- Verify `payment_page` URL is in `Main/urls.py`
- Check template name is `payment_page.html`

### Issue 3: Payment Not Saving
**Symptom**: Can't join even after payment
**Solution**: Check Payment model
- Run: `python manage.py shell`
- Check: `Payment.objects.filter(status='completed')`
- Verify payment record exists with correct user_profile and tournament

### Issue 4: Template Not Found
**Symptom**: TemplateDoesNotExist error
**Solution**: 
- Verify `templates/payment_page.html` exists
- Verify `templates/payment_confirmation.html` exists
- Check template directory in settings.py

---

## Database Queries for Verification

### Check Tournament Payment Settings
```python
from tournifyx.models import Tournament
t = Tournament.objects.get(code='YOUR_CODE')
print(f"is_paid: {t.is_paid}, price: {t.price}")
```

### Check Payment Records
```python
from tournifyx.models import Payment
payments = Payment.objects.all()
for p in payments:
    print(f"User: {p.user_profile.user.username}, Status: {p.status}, Amount: {p.amount}")
```

### Check Who Joined Tournament
```python
from tournifyx.models import TournamentParticipant, Tournament
t = Tournament.objects.get(code='YOUR_CODE')
participants = TournamentParticipant.objects.filter(tournament=t)
for p in participants:
    print(f"Participant: {p.user_profile.user.username}")
```

---

## Success Criteria
✅ Paid tournament creates with is_paid=True and price value
✅ Join attempt redirects to payment page
✅ Payment page displays with all 5 methods
✅ Payment method selection works
✅ Payment confirmation page shows reference number
✅ Payment details submission works
✅ After payment, can successfully join tournament
✅ Player entry created and linked to payment
✅ Tournament dashboard shows participant

---

## Next Steps After Testing
1. Test with all 5 payment methods
2. Test with multiple users joining same paid tournament
3. Test fixture generation when tournament fills
4. Implement host payment verification panel
5. Add payment status display in dashboard
6. Add email notifications for payments

---

**Date**: October 17, 2025
**Version**: 1.0
**Status**: Ready for Testing
