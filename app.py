from oauthtwitter import OAuthApi
import config
from time import time
import requests
import redis

r = redis.StrictRedis(host='localhost', port=6379, db=1)
twitter = OAuthApi(config.TWITTER_CONSUMER_KEY, config.TWITTER_CONSUMER_SECRET, config.TWITTER_ACCESS_TOKEN, config.TWITTER_TOKEN_SECRET)

body = []

def main():
    # retreive followers
    #   returns a dict formatted from the JSON data returned
    ids = []
    print 'getting twitter follower ids 5000 at a time'
    cursor = -1;
    while cursor != 0:
        apiData = twitter.ApiCall('followers/ids', 'GET', { 'cursor' : cursor })

        print 'retrieved (next): %s (%s)' % (len(apiData['ids']), apiData['next_cursor'])

        ids.extend(apiData['ids'])
        cursor = apiData['next_cursor']

    print 'retrieved total followers: %s' % len(ids) 


    # update entries in db but not follower list as unfollowed
    existing = r.zrevrange('followers', 0, -1)
    print 'followers in database: %s' % len(existing)
    print 'checking for unfollows'
    unfollow_ids = []
    follow_ids = []

    for uid in existing:
        if long(uid) in ids: continue

        # update item
        print 'unfollowed by: %s' % uid
        unfollow_ids.append(uid)
        r.zrem('followers', uid)

    # create new entries if they don't exist
    print 'checking for new followers'
    for uid in ids:
        if (r.zrank('followers', uid) > 0):
            continue

        print 'followed by: %s' % uid
        follow_ids.append(uid)
        r.zadd('followers', time(), uid)

    # create email body
    body.append('*** Unfollows ***')
    body.append('')

    # look up info for unfollows
    if unfollow_ids:
        add_details_to_report(unfollow_ids)

    body.append('*** Follows ***')
    body.append('')

    if follow_ids:
        add_details_to_report(follow_ids)

    print '\n'.join(body)

    if not unfollow_ids and not follow_ids: return

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
    
def add_details_to_report(user_ids):
    user_ids_string = ','.join(map(str, user_ids))
    apiData = twitter.ApiCall('users/lookup', 'GET', { 'user_id' : user_ids_string })

    for user in apiData:
        body.append(u'%s (%s)' % (user['screen_name'], user['name']))
        body.append(u'https://twitter.com/#!/%s' % user['screen_name'])
        body.append(unicode(user['description']))
        body.append('')

if __name__ == '__main__':
    main()
