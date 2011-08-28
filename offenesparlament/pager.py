import math

from flask import url_for 

class Pager(object):

    def __init__(self, query, route, args, limit=20, **kwargs):
        self.args = args
        self.route = route 
        self.query = query
        try:
            self.page = int(args.get('page'))
        except:
            self.page = 1
        try:
            self.limit = min(int(args.get('limit')), 200)
        except:
            self.limit = limit

    @property
    def offset(self):
        return (self.page-1)*self.limit

    @property
    def pages(self):
        return int(math.ceil(len(self)/float(self.limit)))

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def next_url(self):
        return self.page_url(self.page + 1) if self.has_next \
               else self.page_url(self.page)

    @property
    def prev_url(self):
        return self.page_url(self.page - 1) if self.has_prev \
               else self.page_url(self.page)

    @property
    def query_args(self):
        return [(k, v.encode('utf-8')) for k, v in self.args.items() \
                if k != 'page']

    def add_url_state(self, arg, value):
        query_args = self.query_args
        query_args.append((arg, value.encode('utf-8')))
        return self.url(query_args)

    def remove_url_state(self, arg, value):
        query_args = [t for t in self.query_args if \
                t != (arg, value.encode('utf-8'))]
        return self.url(query_args)

    def page_url(self, page):
        return self.add_url_state('page', page)

    def url(self, query):
        return url_for(self.route, **dict(query))

    def __iter__(self):
        query = self.query.limit(self.limit)
        query = query.offset(self.offset)
        return query.all().__iter__()

    def __len__(self):
        return self.query.count()

