import os
import json
import requests
from time import sleep, time
from typing import List
from urllib import parse

class LemmyApi:
    def __init__(self, base_url: str, request_interval: int, list_limit: int):
        self.base_url = base_url
        self.last_request = time()
        self.list_limit = list_limit
        self.request_interval = request_interval
        self.requests = []

    def get_api(self, path: str, query: dict, raw = False):
        now = time().strftime("%m/%d/%Y, %H:%M:%S")
        print(f'{now}: Getting from api {path} with query {query}')
        time_diff = time() - self.last_request
        if time_diff < self.request_interval:
            sleep(self.request_interval - time_diff)
        self.last_request = time()
        url = f'{self.base_url}/{path}?{parse.urlencode(query)}'
        self.requests.append({ "date": now, "url": url })
        res = requests.get(url)
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
        return self.get_api('post/list', {
            'community': community,
            'page': page,
            'limit': self.list_limit,
            'sort': sort
        })['posts']
    
    def get_comments(self, post_id: str, community: str) -> List[dict]:
        return self.get_api('comment/list', {
            'post_id': post_id,
            'community_name': community
        })['comments']
    
    def save_requests(self, file_name: str):
        with open(file_name, 'a', encoding='utf-8') as f:
            for req in self.requests:
                f.write(json.dumps(req) + '\n')
        self.requests = []

class Comment:
    def __init__(self, data: dict):
        self.json = json.dumps(data)

class Post:
    def __init__(self, api: LemmyApi, data: dict, comments: List[Comment] = None):
        self.api = api
        self.json = json.dumps(data)
        self.id = data['post']['id']
        self.name = data['post']['name']
        self.published = data['post']['published']
        self.community = data['community']['name']
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
        data = self.api.get_comments(self.id, self.community)
        json_data = json.loads(self.json)
        json_data['comments'] = data
        self.json = json.dumps(json_data)
        self.comments = [Comment(comment) for comment in data]

class PostList:
    def __init__(self, api: LemmyApi, posts: List[Post]):
        self.posts = posts
        self.api = api
        self.ids = [post.id for post in posts]

    def add_to_posts(self, posts: List[dict]):
        for post in posts:
            if post['id'] in self.ids:
                continue
            self.posts.append(Post(self.api, post))
            self.ids.append(post['id'])

    @staticmethod
    def load_from_file(file_name: str, api: LemmyApi):
        if not os.path.exists(file_name):
            return PostList(api, [])
        posts = []
        with open(file_name, 'r', encoding='utf-8') as f:
            line = f.readline()
            while line != None:
                posts.append(Post(api, json.loads(line)))
                line = f.readline()
        return PostList(api, posts)

    @staticmethod
    def load_ids_from_file(file_name: str):
        ids = []
        if not os.path.exists(file_name):
            return ids
        with open(file_name, 'r', encoding='utf-8') as f:
            line = f.readline()
            while line != None:
                data = json.loads(line)
                ids.append(data['id'])
                line = f.readline()
        return ids

    def save_to_file(self, file_name: str):
        with open(file_name, 'a', encoding='utf-8') as f:
            for post in self.posts:
                f.write(post.json + '\n')

def sync_community(api: LemmyApi, community: str, max_page: int):
    saved_posts_file = f'data/{community}.jsonl'
    saved_ids = PostList.load_ids_from_file(saved_posts_file)
    new_posts = PostList(api, [])
    for page in range(1, max_page):
        posts_for_page = api.get_posts(community, 'New', page)
        print(f'{community}: page {page} returned {len(posts_for_page)} posts')
        for post in posts_for_page:
            if post['post']['id'] in saved_ids:
                continue
            new_posts.add_to_posts([post])
    new_posts.save_to_file(saved_posts_file)

def sync_communities(api: LemmyApi, communities: List[str], max_page: int):
    for community in communities:
        try:
            sync_community(api, community, max_page)
        except Exception as e:
            print(e)
            sleep(1)

base_url = 'https://reddthat.com/api/v3'
requests_file = 'data/requests.jsonl'

max_page = 2
list_limit = 5
sync_interval = 12 * 60 * 60
request_interval = 30

api = LemmyApi(base_url, request_interval, list_limit)

communities = [
    'technology@lemmy.world'
]

if not os.path.exists('data'):
    os.mkdir('data')

while True:
    sync_communities(api, communities, max_page)
    api.save_requests(requests_file)
    sleep(sync_interval)