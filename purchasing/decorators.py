# -*- coding: utf-8 -*-

from flask import (
    redirect, url_for, flash, request,
    render_template, current_app
)
from werkzeug.wrappers import Response
from flask_login import current_user
from functools import wraps

def requires_roles(*roles):
    '''
    Takes in a list of roles and checks whether the user
    has access to those role
    '''
    def check_roles(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):

            if current_user.is_anonymous():
                flash('This feature is for city staff only. If you are staff, log in with your pittsburghpa.gov email using the link to the upper right.', 'alert-warning')
                return redirect(request.args.get('next') or '/')
            elif current_user.role.name not in roles:
                flash('You do not have sufficent permissions to do that!', 'alert-danger')
                return redirect(request.args.get('next') or '/')
            return view_function(*args, **kwargs)
        return decorated_function
    return check_roles

def logview(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_app.logger.info('SHERPAVIEW - Viewing page at {}'.format(
            request.path
        ))
        return f(*args, **kwargs)
    return decorated_function

def wrap_form(form=None, form_name=None, template=None):
    '''
    wrap_form takes a form name and a template location, and adds
    the form as 'wrapped_form' into the template. Returns the
    rendered template. Very useful if you need to pass a form into
    a bunch of different views and that form is handled in one place

    Modified from:
    http://flask.pocoo.org/docs/0.10/patterns/viewdecorators/#templating-decorator
    '''
    def add_form(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            _form = form()
            _form_name = form_name if form_name else 'wrapped_form'
            template_name = template
            if not template_name:
                template_name = request.endpoint.replace('.', '/') + '.html'
            ctx = f(*args, **kwargs)
            if isinstance(ctx, Response):
                return ctx
            if ctx is None:
                ctx = {}
            if isinstance(ctx, dict):
                ctx[_form_name] = _form
            elif isinstance(ctx, basestring):
                return ctx
            return render_template(template_name, **ctx)
        return decorated_function
    return add_form

class AuthMixin(object):
    accepted_roles = ['admin', 'superadmin']

    def is_accessible(self):
        if current_user.is_anonymous():
            return False
        if current_user.role.name in self.accepted_roles:
            return True
        return False

class SuperAdminMixin(AuthMixin):
    accepted_roles = ['superadmin']

class ConductorAuthMixin(AuthMixin):
    accepted_roles = ['conductor', 'admin', 'superadmin']
