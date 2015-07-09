# -*- coding: utf-8 -*-

import json
import datetime
from collections import defaultdict

from flask import (
    render_template, request, current_app, flash,
    redirect, url_for, session, abort
)
from flask_login import current_user

from purchasing.database import db
from purchasing.notifications import vendor_signup
from purchasing.opportunities.forms import SignupForm, UnsubscribeForm, ValidationError
from purchasing.opportunities.models import Category, Opportunity, Vendor

from purchasing.opportunities.views.blueprint import blueprint

@blueprint.route('/')
def index():
    '''Landing page for opportunities site
    '''
    return render_template(
        'opportunities/index.html'
    )

@blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
    '''The signup page for vendors
    '''
    all_categories = Category.query.all()
    categories, subcategories = set(), defaultdict(list)
    for category in all_categories:
        categories.add(category.category)
        subcategories['Select All'].append((category.id, category.subcategory))
        subcategories[category.category].append((category.id, category.subcategory))

    form = init_form(SignupForm)

    form.categories.choices = [(None, '---')] + list(sorted(zip(categories, categories))) + [('Select All', 'Select All')]
    form.subcategories.choices = []

    if form.validate_on_submit():

        vendor = Vendor.query.filter(Vendor.email == form.data.get('email')).first()
        form_data = {c.name: form.data.get(c.name, None) for c in Vendor.__table__.columns if c.name not in ['id', 'created_at']}
        form_data['categories'] = []
        subcats = set()

        # manually iterate the form fields
        for k, v in request.form.iteritems():
            if not k.startswith('subcategories-'):
                continue
            else:
                subcat_id = int(k.split('-')[1])
                # make sure the field is checked (or 'on') and we don't have it already
                if v == 'on' and subcat_id not in subcats:
                    subcats.add(subcat_id)
                    subcat = Category.query.get(subcat_id)
                    # make sure it's a valid subcategory
                    if subcat is None:
                        raise ValidationError('{} is not a valid choice!'.format(subcat))
                    form_data['categories'].append(subcat)

        if vendor:
            current_app.logger.info('''
                OPPPUPDATEVENDOR - Vendor updated:
                EMAIL: {old_email} -> {email} at
                BUSINESS: {old_bis} -> {bis_name} signed up for:
                CATEGORIES:
                    {old_cats} ->
                    {categories}'''.format(
                old_email=vendor.email,
                email=form_data['email'],
                old_bis=vendor.business_name,
                bis_name=form_data['business_name'],
                old_cats=[i.__unicode__() for i in vendor.categories],
                categories=[i.__unicode__() for i in form_data['categories']]
            ))

            vendor.update(
                **form_data
            )

            flash("You are already signed up! Your profile was updated with this new information", 'alert-info')

        else:
            current_app.logger.info(
                'OPPNEWVENDOR - New vendor signed up: EMAIL: {email} at BUSINESS: {bis_name} signed up for:\n CATEGORIES: {categories}'.format(
                    email=form_data['email'],
                    bis_name=form_data['business_name'],
                    categories=[i.__unicode__() for i in form_data['categories']]
                )
            )
            vendor = Vendor.create(
                **form_data
            )

            confirmation_sent = vendor_signup(vendor, categories=form_data['categories'])

            if confirmation_sent:
                flash('Thank you for signing up! Check your email for more information', 'alert-success')
            else:
                flash('Uh oh, something went wrong. We are investigating.', 'alert-danger')

        session['email'] = form_data.get('email')
        session['business_name'] = form_data.get('business_name')
        return redirect(url_for('opportunities.index'))

    page_email = request.args.get('email', None)

    if page_email:
        current_app.logger.info('OPPSIGNUPVIEW - User clicked through to signup with email {}'.format(page_email))
        session['email'] = page_email
        return redirect(url_for('opportunities.signup'))

    if 'email' in session:
        if not form.email.validate(form):
            session.pop('email', None)

    display_categories = subcategories.keys()
    display_categories.remove('Select All')

    return render_template(
        'opportunities/signup.html', form=form,
        subcategories=json.dumps(subcategories),
        categories=json.dumps(
            sorted(display_categories) + ['Select All']
        )
    )

@blueprint.route('/manage', methods=['GET', 'POST'])
def manage():
    '''Manage a vendor's signups
    '''
    form = init_form(UnsubscribeForm)
    form_categories = []
    form_opportunities = []

    if form.validate_on_submit():
        email = form.data.get('email')
        vendor = Vendor.query.filter(Vendor.email == email).first()

        if vendor is None:
            form.email.errors = ['We could not find the email {}'.format(email)]

        if request.form.get('button', '').lower() == 'unsubscribe from checked':
            categories = list(set([i.id for i in vendor.categories]).difference(form.categories.data))
            vendor.categories = [Category.query.get(i) for i in categories]

            opportunities = list(set([i.id for i in vendor.opportunities]).difference(form.opportunities.data))
            vendor.opportunities = [opportunities.query.get(i) for i in opportunities]

            db.session.commit()
            flash('Preferences updated!', 'alert-success')

        if vendor:
            for subscription in vendor.categories:
                form_categories.append((subscription.id, subscription.subcategory))
            for subscription in vendor.opportunities:
                form_opportunities.append((subscription.id, subscription.title))

    form.opportunities.choices = form_opportunities
    form.categories.choices = form_categories
    return render_template('opportunities/manage.html', form=form)

class SignupData(object):
    def __init__(self, email, business_name):
        self.email = email
        self.business_name = business_name

def init_form(form):
    data = SignupData(session.get('email'), session.get('business_name'))
    form = form(obj=data)

    return form

def signup_for_opp(form, user, opportunity, multi=False):
    # add the email/business name to the session
    session['email'] = form.data.get('email')
    session['business_name'] = form.data.get('business_name')
    # subscribe the vendor to the opportunity
    vendor = Vendor.query.filter(
        Vendor.email == form.data.get('email'),
        Vendor.business_name == form.data.get('business_name')
    ).first()

    if vendor is None:
        vendor = Vendor(
            email=form.data.get('email'),
            business_name=form.data.get('business_name')
        )
        db.session.add(vendor)
        db.session.commit()

    if multi:
        for opp in opportunity:
            _opp = Opportunity.query.get(int(opp))
            if not _opp.is_public:
                db.session.rollback()
                return False
            vendor.opportunities.append(_opp)
    else:
        vendor.opportunities.append(opportunity)

    if form.data.get('also_categories'):
        # TODO -- add support for categories
        pass

    db.session.commit()
    return True

@blueprint.route('/opportunities', methods=['GET', 'POST'])
def browse():
    '''Browse available opportunities
    '''
    active, upcoming = [], []

    signup_form = init_form(SignupForm)
    if signup_form.validate_on_submit():
        opportunities = request.form.getlist('opportunity')
        if signup_for_opp(
            signup_form, current_user, opportunity=opportunities, multi=True
        ):
            flash('Successfully subscribed for updates!', 'alert-success')
            return redirect(url_for('opportunities.browse'))
        else:
            flash('You can\'t subscribe to that contract!', 'alert-danger')
            return redirect(url_for('opportunities.browse'))

    opportunities = Opportunity.query.filter(
        Opportunity.planned_deadline >= datetime.date.today()
    ).all()

    for opportunity in opportunities:
        if opportunity.is_published():
            active.append(opportunity)
        else:
            upcoming.append(opportunity)

    return render_template(
        'opportunities/browse.html', opportunities=opportunities,
        active=active, upcoming=upcoming, current_user=current_user,
        signup_form=signup_form
    )

@blueprint.route('/opportunities/<int:opportunity_id>', methods=['GET', 'POST'])
def detail(opportunity_id):
    '''View one opportunity in detail
    '''
    opportunity = Opportunity.query.get(opportunity_id)
    if opportunity and opportunity.is_public:
        signup_form = init_form(SignupForm)
        if signup_form.validate_on_submit():
            signup_success = signup_for_opp(signup_form, current_user, opportunity)
            if signup_success:
                flash('Successfully subscribed for updates!', 'alert-success')
                return redirect(url_for('opportunities.detail', opportunity_id=opportunity.id))

        return render_template(
            'opportunities/detail.html', opportunity=opportunity,
            current_user=current_user, signup_form=signup_form
        )
    abort(404)