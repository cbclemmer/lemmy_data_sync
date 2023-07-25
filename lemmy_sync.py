import re
import os
import traceback
import json
import requests
from time import sleep, time
from datetime import datetime
from typing import List
from urllib import parse

# https://github.com/LemmyNet/lemmy
# https://github.com/LemmyNet/lemmy-js-client
# https://reddthat.com

# 2023-07-23T08:20:24.015505
date_pattern = r"(\d{4})-(\d{2})-(\d{2})"
def extract_groups(input_string: str, regex_pattern: re) -> List[str]:
    pattern = re.compile(regex_pattern)
    match = re.search(pattern, input_string)
    if match:
        groups = match.groups()
        return groups
    else:
        return None
    
def get_date(date_str: str):
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
        json_data = json.loads(self.json)
        json_data['comments'] = data
        self.json = json.dumps(json_data)
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

    def save_to_file(self, file_name: str):
        with open(file_name, 'a', encoding='utf-8') as f:
            for post in self.posts:
                f.write(post.json + '\n')

def sync_community(api: LemmyApi, community: str, max_page: int):
    saved_posts_file = f'data/{community}.jsonl'
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
            if diff.days < 1: # Wait until one day has post so comments can be posted
                continue
            new_posts.add_to_posts([post])
    print(f'Saving {len(new_posts.posts)} new posts to {saved_posts_file}')
    new_posts.save_to_file(saved_posts_file)

def sync_communities(api: LemmyApi, communities: List[str], max_page: int):
    for community in communities:
        try:
            sync_community(api, community, max_page)
        except:
            print(traceback.format_exc())
            sleep(10)

base_url = 'https://reddthat.com/api/v3'
requests_file = 'data/requests.jsonl'

max_page = 2
list_limit = 50
sync_interval = int(12 * 60 * 60)
request_interval = 20

api = LemmyApi(base_url, request_interval, list_limit)

communities = [
    'technology@lemmy.world'
]

if not os.path.exists('data'):
    os.mkdir('data')

while True:
    print(f'Syncing Communities')
    sync_communities(api, communities, max_page)
    api.save_requests(requests_file)
    print(f'Communities Synced, sleeping for {sync_interval // (60 * 60)} hours')
    sleep(sync_interval)