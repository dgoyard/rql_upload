#! /usr/bin/env python
##########################################################################
# NSAp - Copyright (C) CEA, 2013
# Distributed under the terms of the CeCILL-B license, as published by
# the CEA-CNRS-INRIA. Refer to the LICENSE file or to
# http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html
# for details.
##########################################################################

# System import
import json
import os
import re
import traceback

# CW import
from cgi import parse_qs
from logilab.mtconverter import xml_escape
from logilab.common.decorators import monkeypatch
from cubicweb import Binary
from cubicweb.view import View
from cubicweb.web import Redirect
from cubicweb.web import formfields
from cubicweb.web import formwidgets
from cubicweb.web import RequestError
from cubicweb.web.views.forms import FieldsForm
from cubicweb.web.views.formrenderers import FormRenderer

# RQL UPLOAD import
from .utils import load_forms
from .formfields import DECLARED_FIELDS


###############################################################################
# CWSearch Widgets
###############################################################################

class CWUploadForm(FieldsForm):
    """ Create a submit button.
    """
    __regid__ = "upload-form"
    title = _("Upload form")

    form_buttons = [formwidgets.SubmitButton(cwaction="apply")]


@monkeypatch(FormRenderer)
def render_content(self, w, form, values):
    """ Overwrite the original processing message when the upload is running.
    """
    if self.display_progress_div:
        w(u'<div id="progress" class="alert alert-warning">')
        w(u'<img width="50" src="{0}"/>'.format(
              self._cw.build_url('data/images/uploading.gif')))
        w(u'<b>Work in progress, please wait ...</b>')
        w(u'</div>')

    self.render_fields(w, form, values)
    self.render_buttons(w, form)


class CWUploadView(View):
    """ Custom view to edit the form generated from the instance
    configuration file.

    .. note::

        The authorized form fields are defined in the global parameter
        'DECLARED_FIELDS' that can be found in the
        'rql_upload.views.formfields.formfields' module.
    """
    __regid__ = "upload-view"
    title = _("Upload form")

    bool_map = {
        "True": True,
        "False": False
    }

    def call(self, **kwargs):
        """ Create the form fields.

        .. note::

            At upload, all field inputs are checked to match the 'check_value'
            regular expressions defined in the 'upload_structure_json' instance
            parameter.
        """
        # Get some parameters
        path = self._cw.relative_path()
        if "?" in path:
            path, param = path.split("?", 1)
            kwargs.update(parse_qs(param))
        form_name = kwargs["form_name"][0]

        # Get the form fields from configuration file
        config = load_forms(self._cw.vreg.config)

        # Create a structure to store values that must be checked before the
        # insertion in the data base
        check_struct = {}
        required_file_fields = {}

        # If json file missing, generate error page
        if config == -1:
            self.w(u'<div class="panel panel-danger">')
            self.w(u'<div class="panel-heading">')
            self.w(u'<h2 class="panel-title">ERROR</h2>')
            self.w(u'</div>')
            self.w(u'<div class="panel-body">')
            self.w(u"<h3>Configuration file not found</h3>")
            self.w(u"Check that the path 'upload_structure_json' "
                    "declared in all-in-one.conf file is set.<br>")
            self.w(u"Then check that the path declared "
                    "(current path:'{0}') corresponds to a "
                    "json file and restart the instance.".format(
                        self._cw.vreg.config["upload_structure_json"]))
            self.w(u'</div>')
            self.w(u'</div>')
            return -1

        # If json can't be read, generate error page
        if config == -2:
            self.w(u'<div class="panel panel-danger">')
            self.w(u'<div class="panel-heading">')
            self.w(u'<h2 class="panel-title">ERROR</h2>')
            self.w(u'</div>')
            self.w(u'<div class="panel-body">')
            self.w(u"<h3>Configuration unknown</h3>")
            self.w(u"The json file configuring the form can't be "
                    "read: {0}".format(
                        self._cw.vreg.config["upload_structure_json"]))
            self.w(u'</div>')
            self.w(u'</div>')
            return -1

        # Create the form
        form = self._cw.vreg["forms"].select(
            "upload-form", self._cw, action="", form_name=form_name)
        try:
            for field in config[form_name]:
                # Remove reserved field keys
                if "rql" in field:
                    rql, dest_name = field.pop("rql").split(":")
                    if dest_name not in field:
                        raise ValueError("{0} not in field attributes.".format(
                            dest_name))
                    if not isinstance(field[dest_name], list):
                        raise ValueError(
                            "{0} field attribute is not a list.".format(
                                dest_name))
                    rset = self._cw.execute(rql)
                    for row in rset.rows:
                        field[dest_name].extend(row)
                field_type = field.pop("type")
                
                # 
                if field_type == "BooleanField" and "value" in field:
                    field["value"] = self.bool_map[field["value"]]
                if "required" in field:
                    field["required"] = self.bool_map[field["required"]]
                if "check_value" in field:
                    check_struct[field["name"]] = field.pop("check_value")
                if (field_type == "FileField" or 
                        field_type == "MultipleFileField"):
                    if not os.path.isdir(
                        self._cw.vreg.config["upload_directory"]):
                        self.w(u"<p class='label label-danger'>{0}: File "
                                "field can't"
                                " be used because the  'upload_directory' "
                                "has not been set in all-in-ine.conf file or its"
                                " path cannot be created ({1})</p>".format(
                                    field.pop("label"),
                                    self._cw.vreg.config["upload_directory"]))
                        continue
                    if "required" in field and field["required"]:
                        required_file_fields[field["name"]] = field["label"]

                # Get the declared field and add it to the form
                if field_type in DECLARED_FIELDS:
                    form.append_field(DECLARED_FIELDS[field_type](**field))
                else:
                    self.w(
                        u"<p class='label label-danger'>'{0}': Unknown field "
                         "</p>".format(field_type))
        except:
            print traceback.format_exc()
            self.w(u'<div class="panel panel-danger">')
            self.w(u'<div class="panel-heading">')
            self.w(u'<h2 class="panel-title">ERROR</h2>')
            self.w(u'</div>')
            self.w(u'<div class="panel-body">')
            self.w(u"<h3>Configuration file syntax error</h3>")
            self.w(u"The configuration file can't be read<br>")
            self.w(u"Please refer to the documentation and make corrections")
            self.w(u'</div>')
            self.w(u'</div>')
            return -1

        # Form processings
        try:
            posted = form.process_posted()

            for required_field, field_label in required_file_fields.items():
                if required_field not in posted:
                    raise RequestError("Required value(s) in {}".format(
                        field_label))

            # Get the form parameters
            inline_params = {}
            deported_params = {}
            for field_name, field_value in posted.iteritems():
                print field_name
                # Filter fields stored in the db or deported on the filesystem
                if isinstance(field_value, Binary):
                    # Check if the field value is valid
                    if field_name in check_struct:
                        file_name = self._cw.form[field_name][0]
                        if re.match(check_struct[field_name],
                                    file_name) is None:
                            raise RequestError(
                                "Find wrong file name '{0}' while searching "
                                "for pattern '{1}'".format(
                                    file_name, check_struct[field_name]))

                    # Add fs item
                    deported_params[field_name] = field_value
                else:
                    # Check if the field value is valid
                    if field_name in check_struct:
                        if re.match(check_struct[field_name],
                                    str(field_value)) is None:
                            raise RequestError(
                                "Find wrong parameter value '{0}' while "
                                "searching for pattern '{1}'".format(
                                    field_value, check_struct[field_name]))

                    # Add db item
                    inline_params[field_name] = str(field_value)

            # Get the eid of the current user
            user_eid = self._cw.execute(
                "Any X Where X is CWUser, X login "
                "'{0}'".format(self._cw.session.login))[0][0]

            # Save the inline parameters in an UploadForm entity
            form_eid = self._cw.create_entity(
                "UploadForm", data=Binary(json.dumps(inline_params)),
                data_format=u"text/json", data_name=u"form.json",
                uploaded_by=user_eid).eid

            # Save deported parameters in UploadFile entities
            upload_file_eids = []
            for field_name, field_value in deported_params.iteritems():
                file_name = self._cw.form[field_name][0]
                basename, extension = os.path.splitext(file_name)
                upload_file_eids.append(self._cw.create_entity(
                    "UploadFile", data=field_value, title=unicode(basename),
                    data_extension=unicode(extension[1:]),
                    data_name=unicode(file_name), uploaded_by=user_eid).eid)

            # Create the CWUpload entity
            upload_eid = self._cw.create_entity(
                "CWUpload",
                form_name=unicode(form_name), result_form=form_eid,
                result_data=upload_file_eids, uploaded_by=user_eid).eid

            # Redirection to the created CWUpload entity
            raise Redirect(self._cw.build_url(eid=upload_eid))
        except RequestError as error:
                self.w(u"<p class='label label-danger'>{0}</p>".format(error))

        # Form rendering
        self.w(u"<legend>'{0}' form</legend>".format(
            form_name))

        form.render(w=self.w, formvalues=self._cw.form)
