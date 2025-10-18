from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import stripe
import os
from datetime import datetime, timedelta
from src.models.member import db, Member

subscription_bp = Blueprint('subscription', __name__)

# Stripe API key (will be set via environment variable in production)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_placeholder')

# Subscription plans (these should match your Stripe product prices)
# Versão CORRIGIDA E FINAL
# Versão 100% CORRIGIDA E FINAL
# Subscription plans (these should match your Stripe product prices)
SUBSCRIPTION_PLANS = {
    'monthly': {
        'price_id': os.getenv('STRIPE_MONTHLY_PRICE_ID', 'price_monthly_placeholder'),
        'amount': 2990,
        'interval': 'month'
    },
    'quarterly': {
        'price_id': os.getenv('STRIPE_QUARTERLY_PRICE_ID', 'price_quarterly_placeholder'),
        'amount': 7990,
        'interval': 'quarter'
    },
    'annual': {
        'price_id': os.getenv('STRIPE_ANNUAL_PRICE_ID', 'price_annual_placeholder'),
        'amount': 29990,
        'interval': 'year'
    }
}





@subscription_bp.route('/create-checkout-session', methods=['POST'])
@jwt_required()
def create_checkout_session():
    """Create a Stripe checkout session for subscription"""
    try:
        current_member_id = get_jwt_identity()
        member = Member.query.get(current_member_id)
        
        if not member:
            return jsonify({'error': 'Member not found'}), 404
        
        data = request.get_json()
        plan = data.get('plan', 'monthly')
        
        if plan not in SUBSCRIPTION_PLANS:
            return jsonify({'error': 'Invalid subscription plan'}), 400
        
        # Create or retrieve Stripe customer
        if not member.stripe_customer_id:
            customer = stripe.Customer.create(
                email=member.email,
                name=member.name,
                metadata={'member_id': member.id}
            )
            member.stripe_customer_id = customer.id
            db.session.commit()
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=member.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': SUBSCRIPTION_PLANS[plan]['price_id'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=data.get('success_url', 'http://localhost:3000/success'),
            cancel_url=data.get('cancel_url', 'http://localhost:3000/cancel'),
            metadata={
                'member_id': member.id,
                'plan': plan
            }
        )
        
        return jsonify({
            'checkout_url': checkout_session.url,
            'session_id': checkout_session.id
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = 'whsec_d95b49e30b89f407a18c4af3f899a8c86345d343ee57aaabd4bac638d90e73fa'

    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle different event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session_completed(session)
    
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        handle_subscription_updated(subscription)
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_deleted(subscription)
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        handle_payment_failed(invoice)
    
    return jsonify({'status': 'success'}), 200


def handle_checkout_session_completed(session):
    """Handle successful checkout session"""
    member_id = session['metadata'].get('member_id')
    plan = session['metadata'].get('plan')
    
    if not member_id:
        return
    
    member = Member.query.get(int(member_id))
    if not member:
        return
    
    # Get subscription details
    subscription_id = session.get('subscription')
    if subscription_id:
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        member.stripe_subscription_id = subscription_id
        member.subscription_status = 'active'
        member.subscription_plan = plan
        member.subscription_start = datetime.utcnow()
        
        # Calculate subscription end date based on plan
        if plan == 'monthly':
            member.subscription_end = datetime.utcnow() + timedelta(days=30)
        elif plan == 'quarterly':
            member.subscription_end = datetime.utcnow() + timedelta(days=90)
        elif plan == 'annual':
            member.subscription_end = datetime.utcnow() + timedelta(days=365)
        
        db.session.commit()


def handle_subscription_updated(subscription):
    """Handle subscription updates"""
    customer_id = subscription['customer']
    member = Member.query.filter_by(stripe_customer_id=customer_id).first()
    
    if not member:
        return
    
    member.subscription_status = subscription['status']
    db.session.commit()


def handle_subscription_deleted(subscription):
    """Handle subscription cancellation"""
    customer_id = subscription['customer']
    member = Member.query.filter_by(stripe_customer_id=customer_id).first()
    
    if not member:
        return
    
    member.subscription_status = 'canceled'
    db.session.commit()


def handle_payment_failed(invoice):
    """Handle failed payment"""
    customer_id = invoice['customer']
    member = Member.query.filter_by(stripe_customer_id=customer_id).first()
    
    if not member:
        return
    
    member.subscription_status = 'past_due'
    db.session.commit()


@subscription_bp.route('/cancel-subscription', methods=['POST'])
@jwt_required()
def cancel_subscription():
    """Cancel current subscription"""
    try:
        current_member_id = get_jwt_identity()
        member = Member.query.get(current_member_id)
        
        if not member:
            return jsonify({'error': 'Member not found'}), 404
        
        if not member.stripe_subscription_id:
            return jsonify({'error': 'No active subscription found'}), 404
        
        # Cancel subscription in Stripe
        stripe.Subscription.delete(member.stripe_subscription_id)
        
        member.subscription_status = 'canceled'
        db.session.commit()
        
        return jsonify({'message': 'Subscription canceled successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/customer-portal', methods=['POST'])
@jwt_required()
def create_customer_portal_session():
    """Create a Stripe customer portal session"""
    try:
        current_member_id = get_jwt_identity()
        member = Member.query.get(current_member_id)
        
        if not member or not member.stripe_customer_id:
            return jsonify({'error': 'No Stripe customer found'}), 404
        
        data = request.get_json()
        return_url = data.get('return_url', 'http://localhost:3000')
        
        # Create portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=member.stripe_customer_id,
            return_url=return_url,
        )
        
        return jsonify({'portal_url': portal_session.url}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

