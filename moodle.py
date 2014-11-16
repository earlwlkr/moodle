import sys
import os
import base64
import unicodedata
import re
import datetime

# external libs
import requests
from bs4 import BeautifulSoup


requests.packages.urllib3.disable_warnings()


def normalize_unicode(s):
    #s = s.decode("utf-8").replace(u"\u0110", "d").replace(u"\u0111", "d").encode("utf-8")
    ret = unicodedata.normalize('NFKD', unicode(s)).encode('ascii', 'ignore')
    return normalize_html_escaped_chars(ret)


def normalize_html_escaped_chars(s):
    return s.replace('&amp;', '&').replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')


def get_input(prompt, max_value=0xFF):
    select = -1
    prompt = '\n\n[?] ' + prompt
    while not (1 <= select <= max_value):
        try:
            select = input(prompt)
        except SyntaxError:
            continue
    return select


class MoodleItem(object):
    def __init__(self, content, link, item_type='None'):
        self.content = content
        self.link = link
        self.item_type = item_type

    def get_content(self):
        return self.content

    def get_link(self):
        return self.link


class CalendarEventItem(MoodleItem):
    def __init__(self, content, link, subj='', due_date=''):
        MoodleItem.__init__(self, content, link)
        self.subject = subj
        self.due_date = due_date

    def get_subject(self):
        return self.subject

    def get_due_date(self):
        return self.due_date

    # string has format like '23:55 Wednesday, 19 November 2014'
    def create_remaining_time_string(self):
        cur = datetime.datetime.now()
        date = datetime.datetime.strptime(self.due_date, '%H:%M %A, %d %B %Y')
        delta = date - cur
        days_part = ''
        hours_part = ''
        if delta.days > 0:
            days_part = '%d ngay, ' % delta.days
        hours = delta.seconds / 3600
        if hours > 0:
            hours_part = '%d gio' % hours
        else:
            days_part = days_part[:-2]
        s = '(%s%s tu hom nay)' % (days_part, hours_part)
        return s


class Requester(object):

    timeout = 8

    def __init__(self):
        self.session = requests.session()

    def get(self, url, **kw):
        return self.request(url, 'GET', **kw)

    def post(self, url, data, **kw):
        return self.request(url, 'POST', data=data, **kw)

    def request(self, url, method, **kw):
        assert method in ('POST', 'GET'), 'Unsupported HTTP Method'

        kw['timeout'] = self.timeout

        r = None
        if method == 'POST':
            r = self.session.post(url, **kw)
        elif method == 'GET':
            r = self.session.get(url, **kw)

        assert r.status_code == 200, r.status_code
        return r


class Moodle(Requester):
    def __init__(self):
        Requester.__init__(self)
        self.soup = None
        self.authed = False

    def login(self, username, password):
        url = 'http://courses.fit.hcmus.edu.vn/moodlenew/login/index.php'
        params = {'username': username, 'password': password}
        print '[*] Dang dang nhap tai khoan', username
        r = self.post(url, data=params, verify=False)
        self.soup = BeautifulSoup(r.text)
        if self.soup.find('span', 'error'):
            print '[!] Loi dang nhap'
        else:
            self.authed = True

    def is_logged_in(self):
        return self.authed

    def get_all_courses(self):
        return [MoodleItem(normalize_unicode(h3.a.string), link=h3.a['href']) 
                for h3 in self.soup.find_all('h3') 
                if 'class' in h3.a.attrs]

    #TODO: include next month's events
    def get_events(self):
        passed_today = False
        events = {}
        for data in self.soup.find_all('td'):
            if not passed_today and 'today' in data.get('class'):
                passed_today = True

            if passed_today and 'hasevent' in data.get('class'):
                event_soup = BeautifulSoup(self.get(data.a['href']).text)
                span = event_soup.find('span', 'current')
                events[span.string] = []

                div = event_soup.find('div', 'eventlist')

                for table in div.find_all('table'):
                    referrer = table.find('div', 'referer')
                    link = referrer.a.get('href')

                    sub_div = referrer.next_sibling
                    subj = normalize_unicode(sub_div.string)

                    due_hour_span = sub_div.next_sibling
                    due_hour = due_hour_span.string

                    td = table.find('td', 'description')
                    content = normalize_unicode(td.p.string)

                    event = CalendarEventItem(content, link, subj, due_hour + ' ' + span.string)

                    events[span.string].append(event)

        return events

    def show_events(self):
        print
        for date, day_events in self.get_events().iteritems():
            print '\nNgay: ', date
            for event in day_events:
                print 'Thoi gian: ', event.get_due_date().split()[0], event.create_remaining_time_string()
                print 'Lop: ', event.get_subject()
                print 'Noi dung: ', event.get_content()
        input()

    def get_course_items(self, course_link):
        course_soup = BeautifulSoup(self.get(course_link).text)
        re_item = re.compile('>(.+?)<')
        items = []

        for div in course_soup.find_all('div', 'activityinstance'):
            for span in div.find_all('span', 'instancename'):
                item_string = normalize_unicode(span)
                item = MoodleItem(re_item.search(item_string).group(1), 
                                  link=div.a['href'])
                if span.span:
                    item.item_type = normalize_unicode(span.span.string.strip())

                items.append(item)

        return items

    def show_courses(self):
        print '\n-- Danh sach mon hoc --'
        courses = self.get_all_courses()
        
        for index, course in enumerate(courses):
            print index + 1, course.get_content()

        course_id = get_input('Nhap so thu tu mon hoc ban muon xem: ', len(courses))

        print '\n-- Danh sach item --'
        course_items = self.get_course_items(courses[course_id - 1].get_link())
        count = 1
        for item in course_items:
            print '%d. %s - %s' % (count, item.get_content(), item.item_type)
            count += 1

        item_id = get_input('Nhap so thu tu item ban muon xem: ', len(course_items))
        item = course_items[item_id - 1]
        #print normalize_unicode(self.session.get(item.get_link()).text)


def login_prompt():
    student_id = ''
    password = ''

    while not student_id or not password:
        try:
            student_id = raw_input('Nhap MSSV: ')
            password = raw_input('Nhap mat khau: ')
        except SyntaxError:
            continue

    return student_id, password


def main():

    if os.path.isfile('moodle.cfg'):
        usr_file = open('moodle.cfg')
        student_id = usr_file.readline().rstrip()
        password = base64.b64decode(usr_file.readline().rstrip())
        usr_file.close()
    else:
        student_id, password = login_prompt()

    moodle = Moodle()
    moodle.login(student_id, password)

    while not moodle.is_logged_in():
        student_id, password = login_prompt()
        moodle.login(student_id, password)
    

    out = open('moodle.cfg', 'w')
    print >> out, student_id
    print >> out, base64.b64encode(password)
    out.close()

    options = {
        1: moodle.show_courses,
        2: moodle.show_events
    }

    task = -1
    while not (0 < task <= len(options)):
        print '\n-- Danh sach tac vu --'
        print '1. Xem mon hoc'
        print '2. Xem danh sach deadline'
        try:
            task = input('\n[?] Nhap so thu tu tac vu ban muon thuc hien: ')
        except EOFError:
            continue
        except SyntaxError:
            continue

    options[task]()
    

if __name__ == '__main__':
    main()