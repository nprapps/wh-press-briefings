#!/usr/bin/env python

"""
Commands that update or process the application data.
"""
import codecs
from collections import defaultdict
import csv
from datetime import datetime, date, timedelta
from glob import glob
import json
import os
from time import sleep

from apiclient.discovery import build
from fabric.api import task
from facebook import GraphAPI
from lxml.html import fromstring
import nltk
from scrapelib import Scraper, FileCache
from slugify import slugify
from twitter import Twitter, OAuth
import unicodecsv

import app_config
import copytext

SEARCH_TERMS = sorted([
    'isis',
    'isil',
    'islamic state',

    'veteran',
    'veterans',
    'shinseki',

    'affordable care act',
    'obamacare',
    'healthcare',
    'health care',
    'insurance',

    'ukraine',
    'ukrainian',
    'crimea',

    'ebola',

    'border',
    'immigration',
    'unaccompanied minors',

    'position',

    'unemployed',
    'unemployment'
])

#SEARCH_TERMS = sorted(['ukraine', 'crimea', 'secret', 'service', 'ebola', 'unemployment', 'keystone', 'ferguson', 'iraq', 'isil', 'isis', 'islamic state', 'military', 'republicans', 'russia', 'syria', 'veterans', 'shinseki', 'benghazi', 'threat', 'immigration', 'border', 'unaccompanied minors', 'economy', 'economic', 'strategy', 'sanctions', 'executive action', 'executive order', 'iraqi', 'iran', 'russian', 'intelligence', 'ukrainian', 'bipartisan', 'africa', 'affordable care act', 'budget', 'insurance', 'jobs', 'humanitarian', 'syrian', 'troops', 'cdc', 'comprehensive', 'afghanistan', 'china', 'putin', 'war', 'enforcement', 'confidence', 'veteran', 'nuclear', 'outbreak', 'airstrikes', 'ambassador', 'fighters', 'russians', 'qaeda', 'pay', 'iraqs', 'wage', 'confront', 'combat', 'israel', 'israeli', 'climate', 'terrorist', 'separatists', 'counterterrorism', 'assad', 'cease-fire', 'healthcare', 'health care', 'obamacare', 'palestine', 'palestinian', 'girls'])

SYNONYMS = [
    ('isis', 'isil', 'islamic state'),
    ('veteran', 'veterans', 'shinseki'),
    ('affordable care act', 'obamacare', 'healthcare', 'health care', 'insurance'),
    ('ukraine', 'ukrainian', 'crimea'),
    ('unemployed', 'unemployment')
]
    
    #('palestine', 'palestinians'),
    #('israel', 'israeli', 'palestine', 'palestinians'),
    #('iraq', 'iraqis', 'iraqs'),
    #('executive order', 'executive action'),
    #('economy', 'economic'),

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
    for index in range(0, 22):
        list = '%s?page=%i' % (ROOT_URL, index)
        print 'parsing %s' % list
        write_corpus(list)

    read_csv()

def write_corpus(page):
    response = s.urlopen(page)
    doc = fromstring(response)
    list = doc.find_class('entry-list')[0]
    writer = unicodecsv.writer(open('data/%s' % CSV_PATH, 'a'))
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
    with open('data/%s' % CSV_PATH, 'rb') as f:
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
            text += '\n%s' % graph.text_content().strip()

        f = codecs.open('data/text/%s.txt' % slug, 'w', encoding='utf-8')
        f.write(text)
        f.close()

@task
def analyze_transcripts():
    for path in glob('data/text/*.txt'):
        _count_words(path)

def _count_words(path):
    print path

    word_count = defaultdict(int)

    with open(path, 'r') as f:
        tokens = nltk.word_tokenize(f.read().decode('utf-8').lower())

    word_counts = nltk.FreqDist(tokens)

    for word, count in word_counts.items():
        word_count[word] = count 
    
    bigrams = nltk.bigrams(tokens)
    bigram_counts = nltk.FreqDist(bigrams)

    for bigram, count in bigram_counts.items():
        word_count['%s %s' % bigram] = count

    trigrams = nltk.trigrams(tokens)
    trigram_counts = nltk.FreqDist(trigrams)

    for trigram, count in trigram_counts.items():
        word_count['%s %s %s' % trigram] = count

    filename = path.split('/')[2]
    count_date = '%s-%s-%s' % (filename.split('-')[0], filename.split('-')[1], filename.split('-')[2])

    with open('data/text/counts/%s.json' % count_date, 'w') as f:
        json.dump({ 'words': word_count }, f)

@task
def analyze_words():
    _generate_word_summary()
    #get_trend_data()
    merge_count_data()
    merge_synonym_counts()

def _generate_word_summary():
    output = {}

    for sunday in all_sundays(2014):
        sunday_str = sunday.strftime('%Y-%m-%d')
        output[sunday_str] = defaultdict(int)

    for path in glob('data/text/counts/*.json'):
        directory, filename = os.path.split(path)
        date, extension = os.path.splitext(filename)

        d = datetime.strptime(date, '%m-%d-%y')

        if d.year != 2014:
            continue

        while d.weekday() != 6:
            d = d - timedelta(days=1)

        sunday = d.strftime('%Y-%m-%d')

        with open(path, 'r') as f:
            data = json.load(f)

            for word in SEARCH_TERMS:
                count = data['words'].get(word, 0)
                output[sunday][word] += count

            with open('data/text/summary/2014.json', 'w') as f:
                f.write(json.dumps(output))

def all_sundays(year):
    d = date(year, 1, 1)                    # January 1st
    d += timedelta(days = 6 - d.weekday())  # First Sunday
    while d.year == year:
        yield d
        d += timedelta(days = 7)

@task
def get_trend_data():
    API_URL = 'https://www.googleapis.com/discovery/v1/apis/trends/v1beta/rest'

    service = build(
        'trends',
        'v1beta',
        developerKey='AIzaSyDL03r4uRooHOZyg9v_arRX4GKrkPf4elw',
        discoveryServiceUrl=API_URL
    )

    output = {}

    for group_of_five in [SEARCH_TERMS[i:i+5] for i in range(0, len(SEARCH_TERMS), 5)]:
        print 'Googling: %s' % group_of_five

        startDate = '2014-01'
        endDate = '2014-12'
        response = service.getGraph(
            terms=group_of_five,
            restrictions_startDate=startDate,
            restrictions_endDate=endDate,
            restrictions_geo='US'
        ).execute()

        for line in response['lines']:
            word = line['term']

            for point in line['points']:
                date = point['date']
                value = point['value']

                if date not in output:
                    output[date] = {}

                output[date][word] = value

        sleep(10)

    with open('data/text/summary/google.json', 'w') as f:
        f.write(json.dumps(output))

@task
def merge_count_data():
    with open('data/text/summary/2014.json', 'r') as wh:
        press_briefings = json.load(wh)

    with open('data/text/summary/google.json', 'r') as g:
        google_trends = json.load(g)

    from xlwt import Workbook
    
    book = Workbook()

    for word in SEARCH_TERMS:
        sheet = book.add_sheet(word)

        header = sheet.row(0)

        for i, col in enumerate(['Week', 'Count']):
            header.write(i, col)

        for i, sunday in enumerate(all_sundays(2014)):
            row = sheet.row(i + 1)

            sunday = sunday.strftime('%Y-%m-%d')
            count = press_briefings[sunday].get(word, 0)
            #google = google_trends[sunday].get(word, 0)
            
            for i, col in enumerate([sunday, count]):
                row.write(i, col)

    book.save('data/text/summary/terms.xls')

@task
def merge_synonym_counts():
    """
    Merge counts for synonyms.
    """
    with open('data/text/summary/2014.json', 'r') as wh:
        press_briefings = json.load(wh)

    from xlwt import Workbook

    book = Workbook()

    for synonyms in SYNONYMS:
        sheet = book.add_sheet('%s (+%i)' % (synonyms[0], len(synonyms)))

        header = sheet.row(0)

        for i, col in enumerate(['Week', 'Count']):
            header.write(i, col)

        for i, sunday in enumerate(all_sundays(2014)):
            row = sheet.row(i + 1)

            sunday = sunday.strftime('%Y-%m-%d')

            count = 0

            for word in synonyms:
                count += press_briefings[sunday].get(word, 0)
            
            for i, col in enumerate([sunday, count]):
                row.write(i, col)

    book.save('data/text/summary/synonyms.xls')

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
