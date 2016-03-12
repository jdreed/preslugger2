#!/usr/bin/python

from flask import Flask, render_template, request, Response
import base64
import csv
import json
import sys
import pprint
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth 
from collections import defaultdict

import cStringIO as StringIO

class FormDefinition(dict):
    def __init__(self, *args, **kwargs):
        super(FormDefinition, self).__init__(*args, **kwargs)
        try:
            fnames = [x['name'] for x in self.fields]
        except KeyError:
            raise ValueError('Form definition contains field entry without name')
        if len(set(fnames)) != len(fnames):
            raise ValueError('Form definition has duplicate field names')

    def __getattr__(self, att):
        return self[att]

    def get_field_by_name(self, name):
        rv = [x for x in self.fields if x.get('name', '') == name]
        try:
            return rv[0]
        except IndexError:
            raise ValueError('Field {} not found'.format(name))
    
    @classmethod
    def load(cls, filename):
        with open(filename, 'r') as infile:
            return cls(json.load(infile))

class Form(object):
    def __init__(self, form_definition, font=('Courier', 10), xoffset=0, yoffset=0, filename=None):
        self.offset = (xoffset, yoffset)
        self.output = StringIO.StringIO() if filename is None else filename
        self.font = font
        self.form_definition = form_definition
        self.canvas = canvas.Canvas(self.output,
                                    pagesize=form_definition.page_size,
                                    bottomup=0)
        self.canvas.setFont(*self.font)

    def coords(self, x, y):
        return (x + self.offset[0], y + self.offset[1])
        
    def center_char_in_slug(self, char):
        text_width = stringWidth(char, *self.font)
        slug_width = self.form_definition.slug_size[0]
        return (slug_width - text_width) / 2.0

    def _rslug(self, x, y):
        x,y = self.coords(x, y)
        self.canvas.roundRect(x, y, *self.form_definition.slug_size, fill=True)

    def slug(self, x, y):
        self._rslug(x, y)

    def text(self, txt, x, y):
        x,y = self.coords(x, y)
        self.canvas.drawString(x, y, txt)

    def set_field(self, field, value):
        f = self.form_definition.get_field_by_name(field)
        if f['_type'] == "numeric":
            self.set_numeric_field(f, value)
        else:
            self.set_text_field(f, value)

    def set_text_field(self, field, value):
        self.text(value, *field['start'])

    def set_numeric_field(self, field, value):
        if len(value) > field['length']:
            raise ValueError('Value too long for field "{0[name]}"'.format(field))
        value = value.rjust(field['length'])
        if not value.strip().replace(' ', '').isdigit():
            raise ValueError('Field "{0[name]}" must be numeric'.format(field))
        for i,n in enumerate(value):
            if n == ' ':
                continue
            col = field['start_col'] + (field['col_width'] * i)
            self.text(n, col + self.center_char_in_slug(n), field['text_row'])
            self.slug(col, field['slug_row'] + (field['row_height'] * int(n)))

    def test_page(self):
        dct = {}
        for f in self.form_definition.fields:
            dct[f['name']] = f['name'].upper() if f['_type'] == 'text' else ''.join(map(str, range(f['length'])))
        self.page(dct)
        self.save()

    def page(self, field_defs):
        self.canvas.setFont(*self.font)
        for k,v in field_defs.items():
            self.set_field(k, v)
        self.canvas.showPage()

    def save(self):
        self.canvas.save()

app = Flask(__name__)

formdef = FormDefinition.load('form_20170.json')
testdate = '3/20/2016'

def parse_csv(csvfile):
    data = {'speech' : defaultdict(list),
            'interview' :defaultdict(list),
            'objective' :defaultdict(list)}
    
    reader = csv.reader(csvfile)
    n_students = 0
    for row in reader:
        if len(row) < 1:
            continue
        (id, team, fname, lname, speech_room, speech_time, interview_room,
         interview_time, homeroom, seat) = map(str.strip, row[0:10])
        n_students += 1
        homeroom = numeric(homeroom)
        speech_room = numeric(speech_room)
        interview_room = numeric(interview_room)
        data['speech'][speech_room].append((id, fname, lname,
                                            datetime.strptime(speech_time,
                                                              '%H:%M:%S').strftime('%H%M')))
        data['interview'][interview_room].append((id, fname, lname,
                                                  datetime.strptime(interview_time,
                                                                 '%H:%M:%S').strftime('%H%M')))
        data['objective'][homeroom].append((id, fname, lname, seat))
    return (data, n_students)

def print_objective(data, room):
    x = Form(formdef)
    for test_num, test_name in ((' 1', '1 - Lang & Lit'),
                                (' 2', '2 - Music'),
                                (' 3', '3 - Science'),
                                (' 4', '4 - Art'),
                                (' 5', '5 - Math'),
                                (' 6', '6 - Economics'),
                                ('11', '11 - Social Science')):
        by_time = sorted(data[room], key=lambda x: int(x[3]), reverse=True)
        for record in by_time:
            name = ' '.join(record[1:3])
            name += ' ({0})'.format(record[0])
            x.page({'Name': name,
                    'Test': test_name,
                    'Teacher': 'Room {0}'.format(room),
                    'Date': testdate,
                    'Test ID': '    {0}'.format(test_num),
                    'Student ID Number': '      {0}'.format(record[0]),
                    'Period': 'Seat {0}'.format(record[3])})
    x.save()
    return x.output.getvalue()

def print_speech(*args):
    return print_speech_interview('Speech', *args)

def print_interview(*args):
    return print_speech_interview('Interview', *args)
    

def print_speech_interview(test, data, room, n_judges):
    x = Form(formdef)
    by_time = sorted(data[room], key=lambda x: int(x[3]))
    for record in by_time:
        name = ' '.join(record[1:3])
        name += ' ({0})'.format(record[0])
        for j in range(1, n_judges + 1):
            x.page({'Name': name, 
                    'Test': 'Interview',
                    'Teacher': 'Room {0}'.format(room),
                    'Date': datetime.strptime(record[3],
                                              '%H%M').strftime('%l:%M %p'),
                    'Test ID': '{0}    9'.format(j),
                    'Period': 'Judge {}'.format(j),
                    'Student ID Number': '      {0}'.format(record[0])})
    x.save()
    return x.output.getvalue()

def send_pdf(filename, content):
    return Response(content,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': 'attachment;filename={}'.format(filename)})

@app.template_filter('json64')
def urlencode(obj):
    return base64.b64encode(json.dumps(obj))

@app.route('/testpage')
def testpage():
    x = Form(formdef)#, filename='out.pdf')
    x.test_page()
    x.save()
    return send_pdf('test_page.pdf', x.output.getvalue())

@app.route('/', methods=('GET', 'POST'))
def index():
    if request.method != 'POST':
        return render_template('index.html')
    formdef = FormDefinition.load('form_20170.json')
    file = request.files['csvfile']
    num_speech = request.form['num_speech']
    num_interview = request.form['num_interview']
    data, n_students = parse_csv(file)
    return render_template('print.html', num_speech=num_speech, num_interview=num_interview, n_students=n_students, **data)

@app.route('/print/<event>', methods=('GET', 'POST'))
def printit(event):
    n_judges = int(request.args.get('num_judges', 3))
    data = json.loads(base64.b64decode(request.form['data']))
    room = request.form['room']
    if event == 'objective':
        return send_pdf('objective-{}.pdf'.format(room), print_objective(data, room))
    if event == 'interview':
        return send_pdf('interview-{}.pdf'.format(room), print_interview(data, room, n_judges))
    if event == 'speech':
        return send_pdf('speech-{}.pdf'.format(room), print_speech(data, room, n_judges))
    return 'ok'

def numeric(s):
    return ''.join([x for x in s if x.isdigit()])


if __name__ == '__main__':
    app.run(debug=True)
