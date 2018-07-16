"""
This module contains the utilities for the Translations app.

.. rubric:: Functions:

:func:`get_validated_language`
    Return the validated given language code or the current active language
    code.
:func:`get_validated_context_info`
    Return the model and iteration information about the validated context.
:func:`get_reverse_relation`
    Return the reverse of a relation for a model.
"""

from django.db import models, transaction
from django.db.models.constants import LOOKUP_SEP
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import get_language
from django.conf import settings

import translations.models


__docformat__ = 'restructuredtext'


def get_validated_language(lang=None):
    """
    Return the validated given language code or the current active language
    code.

    :param lang: The language code to validate, ``None`` means the current
        active language
    :type lang: str or None
    :return: The validated language code
    :rtype: str
    :raise ValueError: If the language code is not included in
        the :data:`~django.conf.settings.LANGUAGES` settings

    >>> from django.utils.translation import activate
    >>> from translations.utils import get_validated_language
    >>> # An already active language
    >>> activate('en')
    >>> get_validated_language()
    'en'
    >>> # A custom language
    >>> get_validated_language('de')
    'de'
    >>> # A language that doesn't exist in `LANGUAGES`
    >>> get_validated_language('xx')
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    ValueError: The language code `xx` is not supported.
    """
    lang = lang if lang else get_language()

    if lang not in [language[0] for language in settings.LANGUAGES]:
        raise ValueError(
            "The language code `{}` is not supported.".format(lang)
        )

    return lang


def get_validated_context_info(context):
    """
    Return the model and iteration information about the validated context.

    :param context: The context to validate
    :type context: ~django.db.models.Model or
        ~collections.Iterable(~django.db.models.Model)
    :return: A tuple representing the context information as (model, iterable)
    :rtype: tuple(type(~django.db.models.Model), bool)
    :raise TypeError: If the context is neither a model instance nor
        an iterable of model instances

    >>> from places.models import Continent
    >>> from translations.utils import get_validated_context_info
    >>> # A model instance
    >>> europe = Continent.objects.create(code="EU", name="Europe")
    >>> get_validated_context_info(europe)
    (<class 'places.models.Continent'>, False)
    >>> # A model iterable
    >>> continents = Continent.objects.all()
    >>> get_validated_context_info(continents)
    (<class 'places.models.Continent'>, True)
    >>> # An empty queryset
    >>> continents.delete()
    (1, {'translations.Translation': 0, 'places.Continent': 1})
    >>> get_validated_context_info(continents)
    (None, True)
    >>> # An empty list
    >>> get_validated_context_info([])
    (None, True)
    >>> # An invalid type
    >>> get_validated_context_info(123)
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    TypeError: `123` is neither a model instance nor an iterable of model instances.
    """
    error_message = '`{}` is neither {} nor {}.'.format(
        context,
        'a model instance',
        'an iterable of model instances'
    )

    if isinstance(context, models.Model):
        model = type(context)
        iterable = False
    elif hasattr(context, '__iter__'):
        if len(context) > 0:
            if isinstance(context[0], models.Model):
                model = type(context[0])
            else:
                raise TypeError(error_message)
        else:
            model = None
        iterable = True
    else:
        raise TypeError(error_message)

    return model, iterable


def get_reverse_relation(model, relation):
    """
    Return the reverse of a relation for a model.

    :param model: The model which contains the relation and which the reverse
        relation will point to
    :type model: type(~django.db.models.Model)
    :param relation: The relation of the model to get the reverse of -
        can include
        :data:`~django.db.models.constants.LOOKUP_SEP` (usually ``__``) to
        represent a deeply nested relation
    :type relation: str
    :return: The reverse of the relation for the model
    :rtype: str
    :raise ~django.core.exceptions.FieldDoesNotExist: If the relation is
        pointing to the fields that don't exist

    >>> # Let's suppose we want a list of all the cities in Europe
    >>> from places.models import Continent, Country, City
    >>> from translations.utils import get_reverse_relation
    >>> europe = Continent.objects.create(code="EU", name="Europe")
    >>> germany = Country.objects.create(
    ...     code="DE",
    ...     name="Germany",
    ...     continent=europe
    ... )
    >>> cologne = City.objects.create(name="Cologne", country=germany)
    >>> # To get the cities:
    >>> get_reverse_relation(Continent, 'countries__cities')
    'country__continent'
    >>> # Using this reverse relation we can query `City` with a `Continent`
    >>> City.objects.filter(country__continent=europe)
    <TranslatableQuerySet [<City: Cologne>]>
    >>> # Done! Cities fetched.
    >>> # An invalid relation of the model
    >>> get_reverse_relation(Continent, 'countries__wrong')
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    django.core.exceptions.FieldDoesNotExist: Country has no field named 'wrong'
    """
    parts = relation.split(LOOKUP_SEP)
    root = parts[0]
    branch = parts[1:]

    field = model._meta.get_field(root)
    reverse_relation = field.remote_field.name

    if branch:
        branch_model = field.related_model
        branch_relation = LOOKUP_SEP.join(branch)
        branch_reverse_relation = get_reverse_relation(
            branch_model,
            branch_relation
        )
        return '{}__{}'.format(
            branch_reverse_relation,
            reverse_relation
        )
    else:
        return reverse_relation


def get_translations_reverse_relation(model, relation=None):
    if relation:
        translations_relation = '{}__{}'.format(relation, 'translations')
    else:
        translations_relation = 'translations'

    return get_reverse_relation(model, translations_relation)


def get_query(model, condition, relation=None):
    translations_reverse_relation = get_translations_reverse_relation(
        model,
        relation
    )
    query = '{}__{}'.format(translations_reverse_relation, condition)
    return query


def get_translations(context, *relations, lang=None):
    r"""
    Return the translations of the context and its relations in a language.

    :param context: The context to fetch the translations for
    :type context: ~django.db.models.query.QuerySet, ~django.db.models.Model
        or list(~django.db.models.Model)
    :param \*relations: The list of relations to fetch the translations for
    :type \*relations: list(str)
    :param lang: The language to fetch the translations for, ``None`` means
        the current active language
    :type lang: str or None
    :return: The translations
    :rtype: ~django.db.models.query.QuerySet
    """
    lang = get_validated_language(lang)
    model, iterable = get_validated_context_info(context)

    if model is None:
        return translations.models.Translation.objects.none()

    if iterable:
        condition = 'pk__in'
        value = [instance.pk for instance in context]
    else:
        condition = 'pk'
        value = context.pk

    queries = []

    if issubclass(model, translations.models.Translatable):
        queries.append(
            models.Q(**{get_query(model, condition): value})
        )

    for relation in relations:
        queries.append(
            models.Q(**{get_query(model, condition, relation): value})
        )

    if len(queries) == 0:
        return translations.models.Translation.objects.none()

    filters = queries.pop()
    for query in queries:
        filters |= query
    queryset = translations.models.Translation.objects.filter(
        language=lang
    ).filter(filters).distinct()

    return queryset


def get_relations_hierarchy(*relations):
    r"""
    Return a dict of first level relations as keys and their nested relations
    as values.

    >>> get_relations_hierarchy()
    {}
    >>> get_relations_hierarchy('countries')
    {'countries': []}
    >>> get_relations_hierarchy('countries__states')
    {'countries': ['states']}
    >>> get_relations_hierarchy(
    ... 'countries__states__cities',
    ... 'countries__states__villages',
    ... 'countries__phone_number',
    ... )
    {'countries': ['states__cities', 'states__villages', 'phone_number']}

    :param \*relations: a list of deeply nested relations to get their
        hierarchy.
    :type \*relations: list(str)
    :return: the first level relations and their nested relations.
    :rtype: dict(str, list(str))
    :raise ValueError: for invalid nested relations
    """
    hierarchy = {}

    for relation in relations:
        parts = relation.split(LOOKUP_SEP)

        if '' in parts:
            raise ValueError(
                '`{}` is not a valid relationship.'.format(
                    LOOKUP_SEP.join(parts)
                )
            )

        root = parts[0]
        nest = LOOKUP_SEP.join(parts[1:])

        hierarchy.setdefault(root, [])
        if nest:
            hierarchy[root].append(nest)

    return hierarchy


def translate(context, *relations, lang=None, translations_queryset=None):
    lang = get_validated_language(lang)

    # ------------ process context
    if isinstance(context, models.QuerySet):
        model = context.model
        is_plural = True
    elif isinstance(context, list):
        model = type(context[0])
        is_plural = True
    elif isinstance(context, models.Model):
        model = type(context)
        is_plural = False
    else:
        raise Exception('`context` is neither a model instance or a queryset or a list')

    # ------------ generate translations queryset if none passed
    if translations_queryset is None:
        translations_queryset = get_translations(
            context,
            *relations,
            lang=lang
        )

    # ------------ convert translations queryset to dict for faster access
    if type(translations_queryset) != dict:
        translations_queryset = translations_queryset.select_related('content_type')
        translations_queryset_dict = {}
        for obj in translations_queryset:
            if obj.content_type.id not in translations_queryset_dict.keys():
                translations_queryset_dict[obj.content_type.id] = {}
            if obj.object_id not in translations_queryset_dict[obj.content_type.id].keys():
                translations_queryset_dict[obj.content_type.id][obj.object_id] = []
            translations_queryset_dict[obj.content_type.id][obj.object_id].append(obj)
        translations_queryset = translations_queryset_dict

    # ------------ translate context itself
    if issubclass(model, translations.models.Translatable):
        content_type = ContentType.objects.get_for_model(model)
        translatable_fields = model.get_translatable_fields()

        # translate obj function
        def translate_obj(obj):
            try:
                obj_translations = translations_queryset[content_type.id][str(obj.id)]
            except KeyError:
                pass
            else:
                for obj_translation in obj_translations:
                    field = model._meta.get_field(obj_translation.field)
                    if field in translatable_fields \
                            and hasattr(obj, obj_translation.field) \
                            and obj_translation.text:
                        setattr(obj, obj_translation.field, obj_translation.text)

        # translate based on plural/singular
        if is_plural:
            for obj in context:
                translate_obj(obj)
        else:
            translate_obj(context)

    # ------------ translate context relations
    relations_dict = get_relations_hierarchy(*relations)

    if len(relations_dict) > 0:
        # translate rel function
        def translate_rel(obj):
            for (relation_key, relation_descendants) in relations_dict.items():
                relation_value = getattr(obj, relation_key, None)
                if relation_value is not None:
                    if isinstance(relation_value, models.Manager):
                        relation_value = relation_value.all()
                    translate(
                        relation_value,
                        *relation_descendants,
                        lang=lang,
                        translations_queryset=translations_queryset
                    )

        # translate based on plural/singular
        if is_plural:
            for obj in context:
                translate_rel(obj)
        else:
            translate_rel(context)


def update_translations(context, lang=None):
    lang = get_validated_language(lang)

    # ------------ process context
    if isinstance(context, models.QuerySet):
        model = context.model
        is_plural = True
    elif isinstance(context, list):
        if len(context) > 0:
            model = type(context[0])
            is_plural = True
        else:
            return
    elif isinstance(context, models.Model):
        model = type(context)
        is_plural = False
    else:
        raise Exception('`context` is neither a model instance or a queryset or a list')

    # ------------ renew transaction
    if issubclass(model, translations.models.Translatable):
        translatable_fields = model.get_translatable_fields()
        try:
            with transaction.atomic():
                # ------------ delete old translations
                translations_queryset = get_translations(
                    context,
                    lang=lang
                )
                translations_queryset.select_for_update().delete()

                # ------------ add new translations
                translations_objects = []

                # add translations function
                def add_translations(obj):
                    for field in translatable_fields:
                        field_value = getattr(obj, field.name, None)
                        if field_value:
                            translations_objects.append(
                                translations.models.Translation(
                                    content_object=obj,
                                    language=lang,
                                    field=field.name,
                                    text=field_value
                                )
                            )

                # translate based on plural/singular
                if is_plural:
                    for obj in context:
                        add_translations(obj)
                else:
                    add_translations(context)

                if len(translations_objects) > 0:
                    translations.models.Translation.objects.bulk_create(translations_objects)
        except Exception:
            raise
