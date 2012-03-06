from oauthtwitter import OAuthApi
from config import oauth_config
from config import aws_config
from config import sendgrid_config
from time import time
import oauth2 as oauth
import boto
import requests

class Followers: 
    twitter = None
    conn = None
    table = None
    table_name = 'followers'
    hash_key = 'follower'
    ids = []
    follow_ids = []
    unfollow_ids = []

    def main(self):
        self.check_schema()
        self.fetch_and_store_followers()
        self.compare_ids()
        self.send_report()

    def send_report(self):
        body = []
        body.append('*** Unfollows ***')
        body.append('')

        # look up info for unfollows
        if self.unfollow_ids:
            self.add_details_to_report(self.unfollow_ids, body)
    
        body.append('*** Follows ***')
        body.append('')

        if self.follow_ids:
            self.add_details_to_report(self.follow_ids, body)
    
        print '\n'.join(body)

        if not self.unfollow_ids and not self.follow_ids: return

        # send email report
        data = {
            'api_user': sendgrid_config['api_user'], 
            'api_key': sendgrid_config['api_key'],
            'to': sendgrid_config['to_address'],
            'from': sendgrid_config['from_address'],
            'subject': 'Twitter follower report',
            'text': '\n'.join(body)
        }

        resp = requests.post('https://sendgrid.com/api/mail.send.json', data=data)
        print resp.content
        
    def add_details_to_report(self, user_ids, body):
        user_ids_string = ','.join(map(str, user_ids))
        apiData = self.twitter.ApiCall('users/lookup', 'GET', { 'user_id' : user_ids_string })

        for user in apiData:
            body.append(u'%s (%s)' % (user['screen_name'], user['name']))
            body.append(u'https://twitter.com/#!/%s' % user['screen_name'])
            body.append(unicode(user['description']))
            body.append('')

    def check_schema(self):
        self.conn = boto.connect_dynamodb(
            aws_access_key_id=aws_config['access_key_id'],
            aws_secret_access_key=aws_config['secret_access_key']
        )

        print 'checking for existing table'
        tables = self.conn.list_tables()
        if self.table_name not in tables:
            print 'table not found, creating'
            followers_table_schema = self.conn.create_schema(
                hash_key_name='follower',
                hash_key_proto_value='S',
                range_key_name='id',
                range_key_proto_value='N'
            )

            self.table = self.conn.create_table(
                name=self.table_name,
                schema=followers_table_schema,
                read_units=3,
                write_units=5
            )
        else:
            print 'table already exists'
            self.table = self.conn.get_table(self.table_name)

    def fetch_and_store_followers(self):
        # setup oauth
        consumer_key    = oauth_config['consumer_key']
        consumer_secret = oauth_config['consumer_secret']
        token           = oauth_config['token']
        token_secret    = oauth_config['token_secret']

        # retreive followers
        self.twitter = OAuthApi(consumer_key, consumer_secret, token, token_secret)

        #returns a dict formatted from the JSON data returned
        print 'getting twitter follower ids 5000 at a time'
        cursor = -1;
        while cursor != 0:
            apiData = self.twitter.ApiCall('followers/ids', 'GET', { 'cursor' : cursor })

            print 'retrieved (next): %s (%s)' % (len(apiData['ids']), apiData['next_cursor'])

            self.ids.extend(apiData['ids'])
            cursor = apiData['next_cursor']

        print 'retrieved total followers: %s' % len(self.ids) 
        
    def compare_ids(self):
        # update entries in db but not follower list as unfollowed
        existing = self.table.query(self.hash_key)
        print 'followers in database: %s' % len(existing)
        print 'checking for unfollows'

        for follower in existing:
            uid = follower['id']
            if long(uid) in self.ids: continue

            # update item
            print 'unfollowed by: %s' % uid
            self.unfollow_ids.append(uid)
            item = self.table.get_item(self.hash_key, str(uid))
            item.delete()

        # create new entries if they don't exist
        print 'checking for new followers'
        for uid in self.ids:
            exists = next((row for row in existing if row['id'] == str(uid)), None)

            if exists: continue

            print 'followed by: %s' % uid
            self.follow_ids.append(uid)
            item_data = {
                'followed_on': time()
            }

            item = self.table.new_item(
                hash_key=self.hash_key,
                range_key=str(uid),
                attrs=item_data 
            )

            item.put()

if __name__ == '__main__':
    Followers().main()
