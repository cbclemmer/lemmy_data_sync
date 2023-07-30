import re
import os
import traceback
import json
import requests
import gzip
from time import sleep, time
from datetime import datetime
from typing import List
from urllib import parse

# main lemmy repo: https://github.com/LemmyNet/lemmy
# js client with types for api: https://github.com/LemmyNet/lemmy-js-client

def get_date(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str.split('T')[0])

class LemmyApi:
    def __init__(self, base_url: str, request_interval: int, list_limit: int):
        self.base_url = base_url
        self.last_request = time()
        self.list_limit = list_limit
        self.request_interval = request_interval
        self.requests = []

    def get_api(self, path: str, query: dict, raw = False):
        now = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
        print(f'\n[{now}] Getting from api {path} with query {query}')
        time_diff = time() - self.last_request
        if time_diff < self.request_interval:
            sleep_time = self.request_interval - time_diff
            print(f'Sleeping for {sleep_time:.2f}s')
            sleep(sleep_time)
        self.last_request = time()
        print('Sending GET Request')
        url = f'{self.base_url}/{path}?{parse.urlencode(query)}'
        self.requests.append({ "date": now, "url": url })
        request_start_time = time()
        res = requests.get(url)
        print(f'[GET {res.status_code}] {url} took {time() - request_start_time:.2f}s')
        if res.status_code != 200:
            raise Exception(f'API returned {res.status_code}: {res.content.decode()}')
        content = res.content.decode()
        if raw:
            return content
        return json.loads(content)

    def get_site(self):
        return self.get_api('site')

    def get_community_info(self, name: str):
        return self.get_api('community', { 'name': name })

    def get_posts(self, community: str, sort: str = 'New', page: int = 1) -> List[dict]:
        print(f'Listing posts for community: {community}')
        return self.get_api('post/list', {
            'community_name': community,
            'page': page,
            'limit': self.list_limit,
            'sort': sort
        })['posts']
    
    def get_comments(self, post_id: str, community_name: str, expected_num: int, page: int = 1, acc: List[dict] = []) -> List[dict]:
        print(f'Loading comments for post {post_id} in {community_name}')
        comments = self.get_api('comment/list', {
            'post_id': post_id,
            'community_name': community_name,
            'max_depth': 10,
            'sort': 'New',
            'limit': 50,
            'page': page
        })['comments']
        for com in comments:
            acc.append(com)
        if len(acc) < expected_num and len(comments) > 0:
            return self.get_comments(post_id, community_name, expected_num, page + 1, acc)
        return acc
    
    def save_requests(self, file_name: str):
        with open(file_name, 'a', encoding='utf-8') as f:
            for req in self.requests:
                f.write(json.dumps(req) + '\n')
        self.requests = []

class Comment:
    def __init__(self, data: dict):
        self.json = json.dumps(data)

class Post:
    def __init__(self, api: LemmyApi, data: dict, community: str, comments: List[Comment] = None):
        self.api = api
        self.json = json.dumps(data)
        self.id = data['post']['id']
        self.name = data['post']['name']
        self.published = data['post']['published']
        self.community = community
        self.comments = None
        self.num_comments = data['counts']['comments']
        if comments is None:
            if 'comments' in data:
                self.comments = [Comment(comment) for comment in data['comments']]
            else:
                self.load_comments()
        else:
            self.comments = comments

    def load_comments(self):
        if self.comments is not None:
            return
        data = self.api.get_comments(self.id, self.community, self.num_comments)
        print(f'Loaded {len(data)} comments for post {self.id}')
        self.comments = [Comment(comment) for comment in data]

class PostList:
    def __init__(self, api: LemmyApi, posts: List[Post], community: str):
        self.posts = posts
        self.api = api
        self.ids = [post.id for post in posts]
        self.community = community

    def add_to_posts(self, posts: List[dict]):
        for post in posts:
            if post['post']['id'] in self.ids:
                continue
            self.posts.append(Post(self.api, post, self.community))
            self.ids.append(post['post']['id'])

    @staticmethod
    def load_from_file(file_name: str, api: LemmyApi, community: str):
        if not os.path.exists(file_name):
            return PostList(api, [])
        posts = []
        with open(file_name, 'r', encoding='utf-8') as f:
            line = f.readline()
            while line != None:
                posts.append(Post(api, json.loads(line), community))
                line = f.readline()
        return PostList(api, posts)

    @staticmethod
    def load_ids_from_file(file_name: str):
        ids = []
        if not os.path.exists(file_name):
            return ids
        with open(file_name, 'r', encoding='utf-8') as f:
            line = f.readline()
            while line != None and line != '':
                data = json.loads(line)
                ids.append(data['post']['id'])
                line = f.readline()
        return ids

    def get_posts_for_day(self, start_idx: int):
        idx = start_idx
        start_day = get_date(self.posts[idx])
        day_posts = [self.posts[idx]]
        while idx < len(self.posts) and start_day == current_day:
            idx += 1
            day_posts.append(self.posts[idx])
            current_day = get_date(self.posts[idx].published).day
        if start_day == current_day:
            return ([], -1)
        return (day_posts, idx)

    def save_to_file(self, file_name: str):
        if len(self.posts) == 0:
            return
        # find the day of the begginning of the post list
        # step index until we hit the first post of the day before
        (_, idx) = get_posts_for_day(0)
        if idx == -1:
            return
        save_posts = []
        while idx is not -1:
            (posts, idx) = get_posts_for_day(idx)
            if idx == -1:
                break
            if len(posts) == 0:
                continue
            for p in posts:
                save_posts.append(p)
            post_date = get_date(posts[0].published)
            with open(f'data/comments_{community}_{post_date.year}_{post_date.month}_{post_date.day}.jsonl.gz', 'r', encoding='utf-8') as f:
                file_data = ''
                for post in posts:
                    for comment in post.comments:
                        file_data += comment.json + '\n'
                f.write(gzip.compress(file_data.encode()))
        with open(file_name, 'a', encoding='utf-8') as f:
            for post in save_posts:
                f.write(post.json + '\n')

def sync_community(api: LemmyApi, community: str, max_page: int, min_post_age: int):
    saved_posts_file = f'data/posts_{community}.jsonl'
    saved_ids = PostList.load_ids_from_file(saved_posts_file)
    print(f'Loaded {len(saved_ids)} ids from {saved_posts_file}')
    new_posts = PostList(api, [], community)
    now = datetime.now()
    for page in range(1, max_page + 1):
        posts_for_page = api.get_posts(community, 'New', page)
        print(f'{community}: page {page} returned {len(posts_for_page)} posts')
        for post in posts_for_page:
            if post['post']['id'] in saved_ids:
                continue
            date = get_date(post['post']['published'])
            diff = now - date
            if diff.hours < min_post_age: # Wait until one day has post so comments can be posted
                continue
            new_posts.add_to_posts([post])
    print(f'Saving {len(new_posts.posts)} new posts to {saved_posts_file}')
    new_posts.save_to_file(saved_posts_file)

def sync_communities(api: LemmyApi, communities: List[str], max_page: int, min_post_age: int):
    for community in communities:
        try:
            sync_community(api, community, max_page, min_post_age)
        except:
            print(traceback.format_exc())
            sleep(10)

def get_with_default(prop: str, obj: dict, default: any) -> any:
    if prop in obj:
        return obj[prop]
    return default

def ensure_prop(prop: str, obj: dict):
    if not prop in obj:
        raise Exception(f'Could not find required property "{prop}" in config.json')
    return obj[prop]

config = {}
if not os.path.exists('config.json'):
    raise Exception('Could not find config.json')

print('Config file found, reading config...')
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.loads(f.read())


base_url = ensure_prop('base_url', config)
if 'api' not in base_url:
    base_url += '/api/v3'

communities = ensure_prop('communities', config)

requests_file = get_with_default('requests_file', config, 'data/requests.jsonl')
max_page = get_with_default('max_page', config, 2)
list_limit = get_with_default('list_limit', config, 50)
sync_interval = get_with_default('sync_interval', config, 12)
sync_interval = int(sync_interval * 60 * 60)
request_interval = get_with_default('request_interval', config, 20)
min_post_age = get_with_default('min_post_age', config, 24)

print(f"""
Config:
base url: {base_url}
communities: {str(communities)}
requests file: {requests_file}
max page: {max_page}
list limit: {list_limit}
sync interval {int(sync_interval / 60 / 60)} hours
request interval: {request_interval} seconds
minimum post age: {min_post_age} hours
""")

api = LemmyApi(base_url, request_interval, list_limit)

if not os.path.exists('data'):
    os.mkdir('data')

while True:
    print(f'Syncing Communities')
    sync_communities(api, communities, max_page, min_post_age)
    api.save_requests(requests_file)
    print(f'Communities Synced, sleeping for {sync_interval // (60 * 60)} hours')
    sleep(sync_interval)