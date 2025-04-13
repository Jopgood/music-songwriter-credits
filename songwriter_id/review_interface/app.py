"""Flask application for the manual review interface."""

import os
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy

# Import database models
from songwriter_id.database.models import Base, Track, SongwriterCredit, IdentificationAttempt

# Create the database instance
db = SQLAlchemy(model_class=Base)


def create_app():
    """Create and configure the Flask application.

    Returns:
        Configured Flask application
    """
    app = Flask(__name__, 
                template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), 'static'))
    
    # Configure the app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_change_in_production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'postgresql://songwriter:password@localhost:5432/songwriter_db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize the database with the app
    db.init_app(app)
    
    # Register routes
    @app.route('/')
    def index():
        """Dashboard homepage."""
        # Get summary statistics
        stats = {}
        with app.app_context():
            try:
                stats['total_tracks'] = db.session.query(Track).count()
                stats['pending_tracks'] = db.session.query(Track).filter_by(identification_status='pending').count()
                stats['identified_tracks'] = db.session.query(Track).filter_by(identification_status='identified').count()
                stats['manual_review_tracks'] = db.session.query(Track).filter_by(identification_status='manual_review').count()
                
                # Get recent tracks for manual review
                recent_tracks = db.session.query(Track)\
                    .filter_by(identification_status='manual_review')\
                    .order_by(Track.updated_at.desc())\
                    .limit(10)
                
                return render_template('index.html', stats=stats, recent_tracks=recent_tracks)
            except Exception as e:
                # For debugging: return a simple message with error details
                return f"Database connection error: {str(e)}"
    
    @app.route('/tracks')
    def list_tracks():
        """List all tracks."""
        # Get filter parameters
        status = request.args.get('status', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Query tracks with filtering
        query = db.session.query(Track)
        if status != 'all':
            query = query.filter_by(identification_status=status)
            
        tracks = query.order_by(Track.updated_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('tracks.html', tracks=tracks, status=status)
    
    @app.route('/tracks/<int:track_id>')
    def track_detail(track_id):
        """Show track details."""
        track = db.session.query(Track).get_or_404(track_id)
        credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
        attempts = db.session.query(IdentificationAttempt).filter_by(track_id=track_id).all()
        
        return render_template('track_detail.html', track=track, credits=credits, attempts=attempts)
    
    @app.route('/tracks/<int:track_id>/review', methods=['GET', 'POST'])
    def review_track(track_id):
        """Review a track's songwriter credits."""
        track = db.session.query(Track).get_or_404(track_id)
        
        if request.method == 'POST':
            # Process form submission for updating credits
            try:
                # Clear existing credits
                db.session.query(SongwriterCredit).filter_by(track_id=track_id).delete()
                
                # Add new credits from form
                songwriter_count = int(request.form.get('songwriter_count', 0))
                for i in range(songwriter_count):
                    if request.form.get(f'songwriter_name_{i}'):
                        credit = SongwriterCredit(
                            track_id=track_id,
                            songwriter_name=request.form.get(f'songwriter_name_{i}'),
                            role=request.form.get(f'role_{i}'),
                            share_percentage=float(request.form.get(f'share_percentage_{i}', 0)),
                            publisher_name=request.form.get(f'publisher_name_{i}'),
                            source_of_info='manual_review',
                            confidence_score=1.0  # Manual review is highest confidence
                        )
                        db.session.add(credit)
                
                # Update track status
                track.identification_status = 'identified'
                track.confidence_score = 1.0
                track.updated_at = datetime.now()
                
                db.session.commit()
                flash('Track credits updated successfully.', 'success')
                return redirect(url_for('track_detail', track_id=track_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating track credits: {str(e)}', 'error')
        
        # Get existing credits and attempts for the track
        credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
        attempts = db.session.query(IdentificationAttempt).filter_by(track_id=track_id).all()
        
        return render_template('review_track.html', track=track, credits=credits, attempts=attempts)
    
    @app.route('/api/tracks/<int:track_id>/credits', methods=['GET'])
    def api_track_credits(track_id):
        """API endpoint for track credits."""
        credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
        result = [
            {
                'credit_id': c.credit_id,
                'songwriter_name': c.songwriter_name,
                'role': c.role,
                'share_percentage': c.share_percentage,
                'publisher_name': c.publisher_name,
                'source_of_info': c.source_of_info,
                'confidence_score': c.confidence_score
            }
            for c in credits
        ]
        
        return jsonify(result)
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """API endpoint for health check."""
        return jsonify({"status": "ok", "message": "Service is running"})
    
    return app
