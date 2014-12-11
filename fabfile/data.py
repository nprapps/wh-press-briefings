#!/usr/bin/env python

"""
Commands that update or process the application data.
"""
import codecs
import csv
from datetime import datetime
from glob import glob
import json
import operator
import os

from fabric.api import task
from facebook import GraphAPI
from lxml.html import fromstring
from nltk.corpus import stopwords
from scrapelib import Scraper, FileCache
from slugify import slugify
from twitter import Twitter, OAuth
import unicodecsv

import app_config
import copytext

ROOT_URL = 'http://www.whitehouse.gov/briefing-room/press-briefings'
CSV_PATH = 'briefing_links.csv'

s = Scraper(requests_per_minute=60)
s.cache_storage = FileCache('press_briefing_cache')
s.cache_write_only = False

@task(default=True)
def update():
    """
    Stub function for updating app-specific data.
    """
    #update_featured_social()

@task
def scrape_briefings():
    os.remove('tmp/%s' % CSV_PATH)

    for index in range(0, 22):
        list = '%s?page=%i' % (ROOT_URL, index)
        print 'parsing %s' % list
        write_corpus(list)

    read_csv()

def write_corpus(page):
    response = s.urlopen(page)
    doc = fromstring(response)
    list = doc.find_class('entry-list')[0]
    writer = unicodecsv.writer(open('tmp/%s' % CSV_PATH, 'a'))
    writer.writerow(['date', 'title', 'transcript_url'])
    for item in list.findall('li'):
        write_row(item, writer)

def write_row(row, writer):
    date = row.find_class('date-line')[0]
    title = row.findall('h3')[0].findall('a')[0]
    href = title.attrib['href']

    if title.text_content().startswith("Press Briefing"):
        writer.writerow([date.text_content(), title.text_content(), href])

def read_csv():
    with open('tmp/%s' % CSV_PATH, 'rb') as f:
        reader = csv.DictReader(f, fieldnames=['date', 'title', 'transcript_url'])
        for row in reader:
            print row
            parse_transcript(row)

def parse_transcript(row):
    if row['date'] != 'date':
        date = datetime.strptime(row['date'], '%B %d, %Y')
        slug_date = datetime.strftime(date, '%m-%d-%y')
        slug = slugify('%s-%s' % (slug_date.decode('utf-8').strip(), row['title'].decode('utf-8').strip()))

    if row['transcript_url'] != 'transcript_url':
        response = s.urlopen('http://whitehouse.gov%s' % row['transcript_url'])
        doc = fromstring(response)
        transcript = doc.get_element_by_id('content')
        paragraphs = transcript.findall('p')

        # for two random days in december the white house decided
        # to put everything in divs
        # i hate everything
        if not paragraphs:
            paragraphs = transcript.findall('div')

        text = ''
        for graph in paragraphs:
            text += '\n %s' % graph.text_content()

        f = codecs.open('data/text/%s.txt' % slug, 'w', encoding='utf-8')
        f.write(text)
        f.close()

@task
def analyze_transcripts():
    for path in glob('data/text/*.txt'):
        _count_words(path)

def _count_words(path):
    IGNORED_WORDS = stopwords.words('english')
    KILL_CHARS = ['.', ',', '"', '\xe2', '\x80', '\x93', '\r', '\n', '\xa6', '?', '\xc2', '\xa0', '\x9d', '\x99', '\x99', '\t', '\x9c', '\xc3', '\xb1']
    DEATH_WORDS = ['\xe2\x80\x93']
    EXTRA_IGNORED_WORDS = ['q', 'carney', 'earnest', 'president', 'mr.']

    print path
    word_count = {}
    payload = {}

    filename = path.split('/')[1]

    with open(path, 'r') as f:
        words = f.read().split(' ')

        for word in words:
            word = word.strip()
            word = word.lower()

            if word in IGNORED_WORDS:
                continue
            elif word == '':
                continue
            else:

                for kill_char in KILL_CHARS:
                    word = word.replace(kill_char, '')

                for death_word in DEATH_WORDS:
                    if death_word in word:
                        break

                if word not in word_count:
                    word_count[word] = 1
                else:
                    word_count[word] += 1

    sorted_word_count = sorted(word_count.items(), key=operator.itemgetter(1))

    date = '%s-%s-%s' % (filename.split('-')[0], filename.split('-')[1], filename.split('-')[2])
    payload[date] = {}

    for k, v in sorted_word_count:
        payload[date][k] = v

    with open('data/text/counts/%s.json' % date, 'w') as f:
        f.write(json.dumps(unicode(payload), indent=4, sort_keys=True))

@task
def update_featured_social():
    """
    Update featured tweets
    """
    COPY = copytext.Copy(app_config.COPY_PATH)
    secrets = app_config.get_secrets()

    # Twitter
    print 'Fetching tweets...'

    twitter_api = Twitter(
        auth=OAuth(
            secrets['TWITTER_API_OAUTH_TOKEN'],
            secrets['TWITTER_API_OAUTH_SECRET'],
            secrets['TWITTER_API_CONSUMER_KEY'],
            secrets['TWITTER_API_CONSUMER_SECRET']
        )
    )

    tweets = []

    for i in range(1, 4):
        tweet_url = COPY['share']['featured_tweet%i' % i]

        if isinstance(tweet_url, copytext.Error) or unicode(tweet_url).strip() == '':
            continue

        tweet_id = unicode(tweet_url).split('/')[-1]

        tweet = twitter_api.statuses.show(id=tweet_id)

        creation_date = datetime.strptime(tweet['created_at'],'%a %b %d %H:%M:%S +0000 %Y')
        creation_date = '%s %i' % (creation_date.strftime('%b'), creation_date.day)

        tweet_url = 'http://twitter.com/%s/status/%s' % (tweet['user']['screen_name'], tweet['id'])

        photo = None
        html = tweet['text']
        subs = {}

        for media in tweet['entities'].get('media', []):
            original = tweet['text'][media['indices'][0]:media['indices'][1]]
            replacement = '<a href="%s" target="_blank" onclick="_gaq.push([\'_trackEvent\', \'%s\', \'featured-tweet-action\', \'link\', 0, \'%s\']);">%s</a>' % (media['url'], app_config.PROJECT_SLUG, tweet_url, media['display_url'])

            subs[original] = replacement

            if media['type'] == 'photo' and not photo:
                photo = {
                    'url': media['media_url']
                }

        for url in tweet['entities'].get('urls', []):
            original = tweet['text'][url['indices'][0]:url['indices'][1]]
            replacement = '<a href="%s" target="_blank" onclick="_gaq.push([\'_trackEvent\', \'%s\', \'featured-tweet-action\', \'link\', 0, \'%s\']);">%s</a>' % (url['url'], app_config.PROJECT_SLUG, tweet_url, url['display_url'])

            subs[original] = replacement

        for hashtag in tweet['entities'].get('hashtags', []):
            original = tweet['text'][hashtag['indices'][0]:hashtag['indices'][1]]
            replacement = '<a href="https://twitter.com/hashtag/%s" target="_blank" onclick="_gaq.push([\'_trackEvent\', \'%s\', \'featured-tweet-action\', \'hashtag\', 0, \'%s\']);">%s</a>' % (hashtag['text'], app_config.PROJECT_SLUG, tweet_url, '#%s' % hashtag['text'])

            subs[original] = replacement

        for original, replacement in subs.items():
            html =  html.replace(original, replacement)

        # https://dev.twitter.com/docs/api/1.1/get/statuses/show/%3Aid
        tweets.append({
            'id': tweet['id'],
            'url': tweet_url,
            'html': html,
            'favorite_count': tweet['favorite_count'],
            'retweet_count': tweet['retweet_count'],
            'user': {
                'id': tweet['user']['id'],
                'name': tweet['user']['name'],
                'screen_name': tweet['user']['screen_name'],
                'profile_image_url': tweet['user']['profile_image_url'],
                'url': tweet['user']['url'],
            },
            'creation_date': creation_date,
            'photo': photo
        })

    # Facebook
    print 'Fetching Facebook posts...'

    fb_api = GraphAPI(secrets['FACEBOOK_API_APP_TOKEN'])

    facebook_posts = []

    for i in range(1, 4):
        fb_url = COPY['share']['featured_facebook%i' % i]

        if isinstance(fb_url, copytext.Error) or unicode(fb_url).strip() == '':
            continue

        fb_id = unicode(fb_url).split('/')[-1]

        post = fb_api.get_object(fb_id)
        user  = fb_api.get_object(post['from']['id'])
        user_picture = fb_api.get_object('%s/picture' % post['from']['id'])
        likes = fb_api.get_object('%s/likes' % fb_id, summary='true')
        comments = fb_api.get_object('%s/comments' % fb_id, summary='true')
        #shares = fb_api.get_object('%s/sharedposts' % fb_id)

        creation_date = datetime.strptime(post['created_time'],'%Y-%m-%dT%H:%M:%S+0000')
        creation_date = '%s %i' % (creation_date.strftime('%b'), creation_date.day)

        # https://developers.facebook.com/docs/graph-api/reference/v2.0/post
        facebook_posts.append({
            'id': post['id'],
            'message': post['message'],
            'link': {
                'url': post['link'],
                'name': post['name'],
                'caption': (post['caption'] if 'caption' in post else None),
                'description': post['description'],
                'picture': post['picture']
            },
            'from': {
                'name': user['name'],
                'link': user['link'],
                'picture': user_picture['url']
            },
            'likes': likes['summary']['total_count'],
            'comments': comments['summary']['total_count'],
            #'shares': shares['summary']['total_count'],
            'creation_date': creation_date
        })

    # Render to JSON
    output = {
        'tweets': tweets,
        'facebook_posts': facebook_posts
    }

    with open('data/featured.json', 'w') as f:
        json.dump(output, f)
