from oauthtwitter import OAuthApi
import config
from time import time
import requests
import redis
from stathat import StatHat

r = redis.StrictRedis(host='localhost', port=6379, db=1)
twitter = OAuthApi(config.TWITTER_CONSUMER_KEY, config.TWITTER_CONSUMER_SECRET, config.TWITTER_ACCESS_TOKEN, config.TWITTER_TOKEN_SECRET)
sh = StatHat()

body = []

def main():
    # retreive followers
    #   returns a dict formatted from the JSON data returned

    compare('followers')
    compare('friends')

    # send email report
    data = {
        'api_user': config.SENDGRID_API_USER, 
        'api_key': config.SENDGRID_API_KEY,
        'to': config.TO_ADDRESS,
        'from': config.FROM_ADDRESS,
        'subject': 'Twitter follower report',
        'text': '\n'.join(body)
    }

    resp = requests.post('https://sendgrid.com/api/mail.send.json', data=data)
    print resp.content

def compare(group):
    ids = []
    print 'getting twitter %s ids 5000 at a time' % group
    cursor = -1;
    while cursor != 0:
        apiData = twitter.ApiCall('%s/ids' % group, 'GET', { 'cursor' : cursor })

        print 'retrieved (next): %s (%s)' % (len(apiData['ids']), apiData['next_cursor'])

        ids.extend(apiData['ids'])
        cursor = apiData['next_cursor']

    print 'retrieved total %s: %s' % (group, len(ids))
    sh.ez_post_value(config.STATHAT_KEY, group, len(ids))

    # update entries in db but not follower list as unfollowed
    existing = r.zrevrange(group, 0, -1)
    print '%s in database: %s' % (group, len(existing))
    print 'checking for subtractions'
    unfollow_ids = []
    follow_ids = []

    for uid in existing:
        if long(uid) in ids: continue

        # update item
        print 'subtracted: %s' % uid
        unfollow_ids.append(uid)
        r.zrem(group, uid)

    # create new entries if they don't exist
    print 'checking for additions'
    for uid in ids:
        if (r.zrank(group, uid) > 0):
            continue

        print 'added: %s' % uid
        follow_ids.append(uid)
        r.zadd(group, time(), uid)

    # create email body
    body.append('*** (%s) Unfollows ***' % group)
    body.append('')

    # look up info for unfollows
    if unfollow_ids:
        add_details_to_report(unfollow_ids)

    body.append('*** (%s) Follows ***' % group)
    body.append('')

    if follow_ids:
        add_details_to_report(follow_ids)

    print '\n'.join(body)

def add_details_to_report(user_ids):
    for ids in chunker(user_ids, 100):
        user_ids_string = ','.join(map(str, ids))
        print user_ids_string
        apiData = twitter.ApiCall('users/lookup', 'GET', { 'user_id' : user_ids_string })

        for user in apiData:
            body.append(u'%s (%s)' % (user['screen_name'], user['name']))
            body.append(u'https://twitter.com/#!/%s' % user['screen_name'])
            body.append(unicode(user['description']))
            body.append('')

def chunker(seq, size):
    return (seq[pos:pos + size] for pos in xrange(0, len(seq), size))

if __name__ == '__main__':
    main()
