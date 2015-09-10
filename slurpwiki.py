#!/usr/bin/env python
"""Slurp SourceForge (Apache Allura) wikis with history and stuff.
"""

import os
import sys
import json
import shutil
import codecs
import datetime
import subprocess

import requests

from bs4 import BeautifulSoup


class SlurpWiki(object):

    work_dir = 'slurpwiki_work'

    def __init__(self, project):
        self.nonapi_base = 'https://sourceforge.net/p/{project}/wiki/'.format(project=project)
        self.api_base = 'https://sourceforge.net/rest/p/{project}/wiki/'.format(project=project)
        self.html_work_dir = os.path.abspath(os.path.join(SlurpWiki.work_dir, 'html'))
        self.md_work_dir = os.path.abspath(os.path.join(SlurpWiki.work_dir, 'md'))
        self.history_work_dir = os.path.abspath(os.path.join(SlurpWiki.work_dir, 'history'))
        self.git_work_dir = os.path.abspath(os.path.join(SlurpWiki.work_dir, 'git'))
        for path in (self.html_work_dir, self.md_work_dir, self.history_work_dir, self.git_work_dir):
            if not os.path.exists(path):
                os.makedirs(path)

    def _cache_page(self, url, page, page_type, rev=None):
        if page_type == 'history':
            cache_name = page + '_history.html'
        elif page_type == 'diff':
            cache_name = page + '_diff_{rev}.html'.format(rev=rev)
        cache_path = os.path.join(self.html_work_dir, cache_name)
        if not os.path.exists(cache_path):
            r = requests.get(url)
            f = codecs.open(cache_path, encoding=r.encoding, mode='w')
            try:
                f.write(requests.get(url).text)
                f.close()
            except:
                os.unlink(cache_path)
                raise
            print('Cached %s to: %s' % (url, cache_path))
        return codecs.open(cache_path, encoding='utf-8').read()

    def write_md(self, page, rev, content, encoding='utf-8'):
        md_path = os.path.join(self.md_work_dir, page + '_{rev}.md'.format(rev=rev))
        f = codecs.open(md_path, encoding=encoding, mode='w')
        try:
            f.write(content)
            f.close()
        except:
            os.unlink(md_path)
            raise
        print('Stored Markdown: %s' % md_path)

    def write_history(self, page, history):
        history_path = os.path.join(self.history_work_dir, page + '.json')
        f = codecs.open(history_path, encoding='utf-8', mode='w')
        try:
            json.dump(history, f)
            f.close()
        except:
            os.unlink(history_path)
            raise
        print('Stored history for page: %s' % page)

    def page_list(self):
        return requests.get(self.api_base).json()['pages']

    def page_history(self, page):
        # won't work for pages with >250 revs
        history_url = self.nonapi_base + page + '/history?limit=250'
        soup = BeautifulSoup(self._cache_page(history_url, page, 'history'), 'html.parser')
        form = soup.find('form', action="diff")
        revs = []
        for tr in form.find_all('tr'):
            rev_info = None
            rev_date = None
            for td in tr.find_all('td'):
                try:
                    contents = td.string.split()
                    rev = int(contents[0])
                    assert contents[1] == 'by'
                    username = contents[-1].strip('()')
                    name = ' '.join(contents[2:4])
                    rev_info = (rev, username, name)
                    continue
                except:
                    pass
                try:
                    span = td.find('span')
                    assert span.attrs['title'].endswith(' UTC')
                    rev_date = datetime.datetime.strptime(span.attrs['title'], '%a %b %d, %Y %I:%M %p %Z')
                    rev_date = rev_date.isoformat()
                    continue
                except:
                    pass
            if rev_info is not None and rev_date is not None:
                revs.append(rev_info + (rev_date,))
        assert revs, 'Could not find any revisions, parsing error?'
        self.write_history(page, revs)
        return revs

    def all_page_histories(self):
        r = {}
        for page in self.page_list():
            r[page] = self.page_history(page)
        return r

    def page_version(self, page, rev):
        diff_url = self.nonapi_base + page + '/diff?v2={rev}&v1={rev}'.format(rev=rev)
        soup = BeautifulSoup(self._cache_page(diff_url, page, 'diff', rev=rev), 'html.parser')
        # seriously who doesn't use ids or classes at all?
        for div_tag in soup.find_all('div'):
            if div_tag.attrs.get('style', '') == 'font-family: fixed-width, monospace; padding: 10px;':
                content = []
                # most "lines" start with a newline
                for line in div_tag.strings:
                    # there's an extra space at the beginning of every line
                    if line[0] == ' ':
                        line = line[1:]
                    elif line[0:2] == '\n ':
                        line = '\n' + line[2:]
                    # there's an extra space at the end of every line
                    if len(line) and line[-1] == ' ':
                        line = line[:-1]
                    content.append(line)
                self.write_md(page, rev, ''.join(content))
                break
        else:
            raise Exception("Couldn't find page div!")

    def all_page_versions(self):
        for page in self.page_list():
            for page_history in self.page_history(page):
                page_rev = page_history[0]
                self.page_version(page, page_rev)

    def build_git_repo(self):
        os.chdir(self.git_work_dir)
        if not os.path.exists('.git'):
            subprocess.check_call(['git', 'init', '.'])
        for histfile in os.listdir(self.history_work_dir):
            page = os.path.splitext(histfile)[0]
            histfile_path = os.path.join(self.history_work_dir, histfile)
            history = json.load(codecs.open(histfile_path, encoding='utf-8'))
            for rev in reversed(history):
                versioned_page = os.path.join(self.md_work_dir,
                                              '{page}_{rev}.md'.format(page=page, rev=rev[0]))
                unversioned_page = os.path.join(self.git_work_dir, '{page}.md'.format(page=page))
                shutil.copy(versioned_page, unversioned_page)
                cmd = ['git', 'status', '--short']
                if not subprocess.check_output(cmd):
                    # apparently there are empty commits in SF wikis
                    continue
                cmd = ['git', 'add', '{page}.md'.format(page=page)]
                print('executing: %s' % ' '.join(cmd))
                subprocess.check_call(cmd)
                cmd = ['git',
                       'commit',
                       '--author={name} <{username}@users.sourceforge.net>'.format(name=rev[2],
                                                                                   username=rev[1]),
                       '--date={date}'.format(date=rev[3]),
                       '--message={page} version {rev}'.format(page=page, rev=rev[0])]
                print('executing: %s' % ' '.join(cmd))
                subprocess.check_call(cmd)

if __name__ == '__main__':
    assert sys.argv[1], 'usage: slurpwiki.py <sf-project-name>'
    slurp = SlurpWiki(sys.argv[1])
    slurp.all_page_versions()
    slurp.build_git_repo()
