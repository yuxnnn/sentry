import React from 'react';

import ApiMixin from '../mixins/apiMixin';
import LoadingIndicator from '../components/loadingIndicator';
import ProjectState from '../mixins/projectState';
import {GenericField} from '../components/forms';
import {t, tct} from '../locale';

const FIELDS = {
  name: {
    name: 'name',
    type: 'string',
    label: t('Project name'),
    placeholder: 'e.g. My Service Name',
  },
  slug: {
    name: 'slug',
    type: 'string',
    label: t('Short name'),
    help: t('A unique ID used to identify this project.'),
  },
  team: {
    name: 'team',
    type: 'choice',
    label: t('Team'),
    choices: [],
  },
  resolve_age: {
    name: 'resolve_age',
    type: 'range',
    label: t('Auto resolve'),
    help: t('Automatically resolve an issue if it hasn\'t been seen for this amount of time.'),
    min: 0,
    max: 168,
    step: 1,
    allowedValues: (() => {
      let i = 0;
      let values = [];
      while (i <= 168) {
        values.push(i);
        if (i < 12) {
          i += 1;
        } else if (i < 24) {
          i += 3;
        } else if (i < 36) {
          i += 6;
        } else if (i < 48) {
          i += 12;
        } else {
          i += 24;
        }
      }
      return values;
    })(),
    formatLabel: (val) => {
      val = parseInt(val, 10);
      if (val === 0) {
          return 'Disabled';
      } else if (val > 23 && val % 24 === 0) {
          val = (val / 24);
          return val + ' day' + (val != 1 ? 's' : '');
      }
      return val + ' hour' + (val != 1 ? 's' : '');
    },
    required: false,
  },
  securityToken: {
    name: 'securityToken',
    type: 'string',
    label: t('Security token'),
    help: t('Outbound requests matching Allowed Domains will have the header "X-Sentry-Token: {token}" appended.'),
    required: false,
  },
};


const ProjectGeneralSettings = React.createClass({
  propTypes: {
    project: React.PropTypes.object.isRequired,
  },

  mixins: [ApiMixin, ProjectState],

  getInitialState() {
    let project = this.props.project;
    let initialData = {
      name: project.name,
      slug: project.slug,
      securityToken: project.securityToken,
    };
    let fields = {...FIELDS};
    project.config.forEach((f) => {
      fields[f.name] = f;
      initialData[f.name] = project.options[f.name];
    });

    return {
      loading: false,
      error: false,

      initialData: initialData,
      formData: {...initialData},
      fields: fields,
      errors: {},
    };
  },

  componentWillReceiveProps(nextProps) {
    let location = this.props.location;
    let nextLocation = nextProps.location;
    if (location.pathname != nextLocation.pathname || location.search != nextLocation.search) {
      this.remountComponent();
    }
  },

  remountComponent() {
    this.setState(this.getInitialState(), this.fetchData);
  },

  changeField(name, value) {
    // upon changing a field, remove errors
    let errors = this.state.errors;
    delete errors[name];
    this.setState({formData: {
      ...this.state.formData,
      [name]: value,
    }, errors: errors});
  },

  getEndpoint() {
    let {orgId, projectId} = this.props.params;
    return `/projects/${orgId}/${projectId}/`;
  },

  onSubmit() {
    this.api.request(this.getEndpoint(), {
      data: this.state.formData,
      method: 'PUT',
      success: this.onSaveSuccess.bind(this, data => {
        let formData = {};
        data.config.forEach((field) => {
          formData[field.name] = field.value || field.defaultValue;
        });
        this.setState({
          formData: formData,
          initialData: Object.assign({}, formData),
          errors: {}
        });
      }),
      error: this.onSaveError.bind(this, error => {
        this.setState({
          errors: (error.responseJSON || {}).errors || {},
        });
      }),
      complete: this.onSaveComplete
    });
  },

  renderLoading() {
    return (
      <div className="box">
        <LoadingIndicator />
      </div>
    );
  },

  renderField(name) {
    let field = this.state.fields[name];
    if (name === 'team') {
      field = {
        ...field,
        choices: this.getOrganization().teams
          .filter(o => o.isMember)
          .map(o => [o.id, o.slug]),
      };
      if (field.choices.length === 1)
        return null;
    }

    return (
      <GenericField
        config={field}
        formData={this.state.formData}
        formErrors={this.state.errors}
        onChange={this.changeField.bind(this, field.name)} />
    );
  },

  render() {
    if (this.state.loading)
      return this.renderLoading();

    return (
      <div>
        <h2>{t('Project Settings')}</h2>

          <form className="form-stacked">
            <div className="box">
              <div className="box-header">
              <h3>{t('Project Details')}</h3>
            </div>
            <div className="box-content with-padding">
              {this.renderField('name')}
              {this.renderField('slug')}
              {this.renderField('team')}
            </div>
          </div>

          <div className="box">
            <div className="box-header">
              <h3>{t('Email')}</h3>
            </div>
            <div className="box-content with-padding">
              {this.renderField('mail:subject_prefix')}
            </div>
          </div>

          <div className="box">
            <div className="box-header">
              <h3>{t('Event Settings')}</h3>
            </div>
            <div className="box-content with-padding">
              {this.renderField('sentry:default_environment')}
              {this.renderField('resolve_age')}
              <p><small><strong>Note: Enabling auto resolve will immediately resolve anything that has not been seen within this period of time. There is no undo!</strong></small></p>
            </div>
          </div>

          <div className="box">
            <div className="box-header">
              <h3>{t('Data Privacy')}</h3>
            </div>
            <div className="box-content with-padding">
              {this.renderField('sentry:scrub_data')}
              {this.renderField('sentry:scrub_defaults')}
              {this.renderField('sentry:sensitive_fields')}
              {this.renderField('sentry:safe_fields')}
              {this.renderField('sentry:scrub_ip_address')}
            </div>
          </div>

          <div className="box">
            <div className="box-header">
              <h3>{t('Client Security')}</h3>
            </div>
            <div className="box-content with-padding">

              <p>{tct('Configure origin URLs which Sentry should accept events from. This is used for communication with clients like [link].', {
                link: <a href="https://github.com/getsentry/raven-js">raven-js</a>
              })} {tct('This will restrict requests based on the [Origin] and [Referer] headers.', {
                Origin: <code>Origin</code>,
                Referer: <code>Referer</code>,
              })}</p>
              {this.renderField('sentry:origins')}
              {this.renderField('sentry:scrape_javascript')}
              {this.renderField('securityToken')}
              {this.renderField('sentry:blacklisted_ips')}
            </div>
          </div>

          <div className="form-actions">
            <button type="submit" className="btn btn-primary btn-lg">{t('Save Changes')}</button>
          </div>
        </form>
      </div>
    );
  }
});

export default ProjectGeneralSettings;
