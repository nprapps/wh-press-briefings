#!/usr/bin/env python

from glob import glob
import json

from flask import Flask, make_response, render_template
from werkzeug.debug import DebuggedApplication

import app_config
from render_utils import make_context, smarty_filter, urlencode_filter
import static

app = Flask(__name__)
app.debug = app_config.DEBUG

app.add_template_filter(smarty_filter, name='smarty')
app.add_template_filter(urlencode_filter, name='urlencode')

# Example application views
@app.route('/')
def index():
    """
    Example view demonstrating rendering a simple HTML page.
    """
    context = make_context()

    with open('data/featured.json') as f:
        context['featured'] = json.load(f)

    context['links'] = []

    for file in glob('data/text/*.txt'):
        filename = file.split('/')[2].split('.')[0]
        context['links'].append(filename)

    return make_response(render_template('index.html', **context))

@app.route('/briefing/<string:slug>/')
def briefing(slug):
    context = make_context()

    date = '%s-%s-%s' % (slug.split('-')[0], slug.split('-')[1], slug.split('-')[2])

    context['date'] = date

    with open('data/text/counts/%s.json' % date) as f:
        context['briefing'] = json.load(f)

    context['slug'] = slug

    return make_response(render_template('briefing.html', **context))

@app.route('/word/<string:slug>/')
def word(slug):
    context = make_context()

    data = {
        'reporter_word_count': [],
        'secretary_word_count': []
    }

    for file in glob('data/text/counts/*.json'):
        with open(file) as f:
            transcript_data = json.load(f)

            date = file.split('/')[3].split('.')[0]

            reporter_words = transcript_data['reporters']['words']
            secretary_words = transcript_data['secretary']['words']

            for word in reporter_words:
                for k, v in word.iteritems():
                    if k == slug:
                        data['reporter_word_count'].append({
                            date: v
                        })
                        break

            for word in secretary_words:
                for k, v in word.iteritems():
                    if k == slug:
                        data['secretary_word_count'].append({
                            date: v
                        })
                        break

    context['data'] = json.dumps(data)

    return make_response(render_template('word.html', **context))

@app.route('/comments/')
def comments():
    """
    Full-page comments view.
    """
    return make_response(render_template('comments.html', **make_context()))

@app.route('/widget.html')
def widget():
    """
    Embeddable widget example page.
    """
    return make_response(render_template('widget.html', **make_context()))

@app.route('/test_widget.html')
def test_widget():
    """
    Example page displaying widget at different embed sizes.
    """
    return make_response(render_template('test_widget.html', **make_context()))

app.register_blueprint(static.static)

# Enable Werkzeug debug pages
if app_config.DEBUG:
    wsgi_app = DebuggedApplication(app, evalex=False)
else:
    wsgi_app = app

# Catch attempts to run the app directly
if __name__ == '__main__':
    print 'This command has been removed! Please run "fab app" instead!'
