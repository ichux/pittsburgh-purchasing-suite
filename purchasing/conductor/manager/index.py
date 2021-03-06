# -*- coding: utf-8 -*-

from flask import request, render_template, current_app
from flask_login import current_user

from purchasing.decorators import requires_roles
from purchasing.database import db

from purchasing.data.stages import Stage
from purchasing.data.flows import Flow
from purchasing.data.companies import Company
from purchasing.data.contracts import ContractBase, ContractProperty, ContractType
from purchasing.data.contract_stages import ContractStage

from sqlalchemy.orm import aliased

from purchasing.users.models import User, Role, Department

from purchasing.conductor.manager import blueprint

@blueprint.route('/')
@requires_roles('conductor', 'admin', 'superadmin')
def index():
    '''Main conductor index page/splash view

    Renders two tables that conductors can use to track their progress:
    ``in_progress``, which contains all of the
    :py:class:`~purchasing.data.contracts.ContractBase` objects that are
    currently being worked on by a conductor. ``in_progress`` contracts
    are generated by selecting only :py:class:`~purchasing.data.contracts.ContractBase`
    objects that have a ``parent_id``, have an existing ``flow``,
    non-null ``entered`` current contract stage, and are neither ``is_archived`` nor
    ``is_visible``.

    ``all_contracts`` contains all contracts that are eligible
    to show up in conductor to be worked on. These are filtered based on the
    :py:class:`~purchasing.data.contracts.ContractType`
    ``managed_by_conductor`` field. Additionally, these are
    filtered by having no ``children``, and ``is_visible`` set to True

    .. seealso:: :py:class:`~purchasing.data.contracts.ContractBase`,
        :py:class:`~purchasing.data.contract_stages.ContractStage`,
        :py:class:`~purchasing.data.flows.Flow`

    :status 200: Render the main conductor index page
    '''
    parent = aliased(ContractBase)

    parent_specs = db.session.query(
        ContractBase.id, ContractProperty.value,
        parent.expiration_date, parent.contract_href,
        Company.company_name
    ).join(
        ContractProperty,
        ContractBase.parent_id == ContractProperty.contract_id
    ).join(
        parent, ContractBase.parent
    ).outerjoin(
        Company, parent.companies
    ).filter(
        db.func.lower(ContractProperty.key) == 'spec number',
        ContractType.managed_by_conductor == True
    ).subquery()

    in_progress = db.session.query(
        db.distinct(ContractBase.id).label('id'),
        ContractProperty.value.label('spec_number'),
        parent_specs.c.value.label('parent_spec'),
        parent_specs.c.expiration_date.label('parent_expiration'),
        parent_specs.c.contract_href.label('parent_contract_href'),
        ContractBase.description, Flow.flow_name,
        Stage.name.label('stage_name'), ContractStage.entered,
        User.first_name, User.email,
        Department.name.label('department'),
        db.func.array_remove(
            db.func.array_agg(parent_specs.c.company_name),
            None
        ).label('companies')
    ).outerjoin(Department).join(
        ContractStage, db.and_(
            ContractStage.stage_id == ContractBase.current_stage_id,
            ContractStage.contract_id == ContractBase.id,
            ContractStage.flow_id == ContractBase.flow_id
        )
    ).join(
        Stage, Stage.id == ContractBase.current_stage_id
    ).join(
        Flow, Flow.id == ContractBase.flow_id
    ).outerjoin(
        ContractProperty, ContractProperty.contract_id == ContractBase.id
    ).outerjoin(
        parent_specs, ContractBase.id == parent_specs.c.id
    ).join(User, User.id == ContractBase.assigned_to).filter(
        ContractStage.flow_id == ContractBase.flow_id,
        ContractStage.entered != None,
        ContractBase.assigned_to != None,
        ContractBase.is_visible == False,
        ContractBase.is_archived == False
    ).group_by(
        ContractBase.id,
        ContractProperty.value.label('spec_number'),
        parent_specs.c.value.label('parent_spec'),
        parent_specs.c.expiration_date.label('parent_expiration'),
        parent_specs.c.contract_href.label('parent_contract_href'),
        ContractBase.description, Flow.flow_name,
        Stage.name.label('stage_name'), ContractStage.entered,
        User.first_name, User.email,
        Department.name.label('department')
    ).all()

    all_contracts = db.session.query(
        ContractBase.id, ContractBase.description,
        ContractBase.financial_id, ContractBase.expiration_date,
        ContractProperty.value.label('spec_number'),
        ContractBase.contract_href, ContractBase.department,
        User.first_name, User.email,
        db.func.array_remove(
            db.func.array_agg(Company.company_name),
            None
        ).label('companies')
    ).join(ContractType).outerjoin(
        User, User.id == ContractBase.assigned_to
    ).outerjoin(Company, ContractBase.companies).outerjoin(
        Department, Department.id == ContractBase.department_id
    ).outerjoin(
        ContractProperty, ContractProperty.contract_id == ContractBase.id
    ).filter(
        ContractType.managed_by_conductor == True,
        db.func.lower(ContractProperty.key) == 'spec number',
        ContractBase.children == None,
        ContractBase.is_visible == True
    ).group_by(
        ContractBase.id, ContractBase.description,
        ContractBase.financial_id, ContractBase.expiration_date,
        ContractProperty.value.label('spec_number'),
        ContractBase.contract_href, ContractBase.department,
        User.first_name, User.email
    ).order_by(ContractBase.expiration_date).all()

    conductors = User.query.join(Role, User.role_id == Role.id).filter(
        Role.name == 'conductor',
        User.email != current_user.email
    ).all()

    current_app.logger.info('CONDUCTOR INDEX - Conductor index page view')

    return render_template(
        'conductor/index.html',
        in_progress=in_progress, _all=all_contracts,
        current_user=current_user,
        conductors=[current_user] + conductors,
        path='{path}?{query}'.format(
            path=request.path, query=request.query_string
        )
    )
