from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt
from src.models.member import db, Member
from datetime import timedelta

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new member"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or not data.get('email') or not data.get('password') or not data.get('name'):
            return jsonify({'error': 'Email, password, and name are required'}), 400
        
        # Check if user already exists
        if Member.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already registered'}), 409
        
        # Hash password
        password_hash = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
        # Create new member
        new_member = Member(
            email=data['email'],
            password_hash=password_hash,
            name=data['name']
        )
        
        db.session.add(new_member)
        db.session.commit()
        
        # Create access token
        access_token = create_access_token(
            identity=str(new_member.id),
            expires_delta=timedelta(days=30)
        )
        
        return jsonify({
            'message': 'Member registered successfully',
            'access_token': access_token,
            'member': new_member.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login a member"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find member
        member = Member.query.filter_by(email=data['email']).first()
        
        if not member or not bcrypt.check_password_hash(member.password_hash, data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Create access token
        access_token = create_access_token(
            identity=str(member.id),
            expires_delta=timedelta(days=30)
        )
        
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'member': member.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_member():
    """Get current member information"""
    try:
        current_member_id = get_jwt_identity()
        member = Member.query.get(current_member_id)
        
        if not member:
            return jsonify({'error': 'Member not found'}), 404
        
        return jsonify(member.to_dict()), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/check-membership', methods=['GET'])
@jwt_required()
def check_membership():
    """Check if current user has an active membership"""
    try:
        current_member_id = get_jwt_identity()
        member = Member.query.get(current_member_id)
        
        if not member:
            return jsonify({'error': 'Member not found'}), 404
        
        return jsonify({
            'is_active': member.is_active_member(),
            'subscription_status': member.subscription_status,
            'subscription_plan': member.subscription_plan
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

