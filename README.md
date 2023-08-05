# Sync Lemmy Data
This repository uses a lemmy server to scrape data from its api. It will continously run every few hours (default: 12 hours) to pull data from communities. It will only sync data that is a certain amount of time old (default: 24 hours) so that enough comments can be created that it is worth saving. It will only retrieve posts that have not been synced yet.
  
## Usage
The repository depends on a `config.json` file at the root of the project directory. Here is an example file and the default values:
```
{
  "base_url": "https://reddthat.com", // (Required) The lemmy server to send calls to
  "communities": [ "technology@lemmy.world" ], // (Required) the communities to sync
  "requests_file": "requests.jsonl", // (Optional) The file to create that will contain all of the api call data sent to the server
  "max_page": 2, // (Optional) the number of pages to sync
  "list_limit": 50, // (Optional) the number of posts to sync per page
  "sync_interval": 12 // (Optional) number of hours per sync
  "request_interval": 20 // (Optional) the number of seconds between api calls to rate limit server
  "minimun_post_age": 12 // (Optional) the number of hours since the post was created needed to be able to save the post and comment data
}
```

## Files
These are the files created by the service. The system waits until it has a full day of posts to save their comment and post data.

#### The requests file
The file name is taken from the `requests_file` property that stores all request data sent to the server.  
  
#### The Post data
Each community will have their own jsonl file that holds the post data for all the posts that are synced.  
In the form of `community.jsonl`.  

#### Comment Data
Each day a new comment file will be created. The file is compressed using gzip to save space.
