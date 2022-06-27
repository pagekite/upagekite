# Copyright (C) 2020-2022, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Commercial licenses are for sale. See the files README.md and COPYING.txt
# for more details.


def xml_encode(s):
  return (str(s)
    .replace('&', '&amp;')
    .replace('"', '&quot;')
    .replace('<', '&lt;')
    .replace('>', '&gt;'))


def to_xml(name, data, indent='', attrs=''):
  if isinstance(data, dict):
    if 'value' in data:
      attrs = data
      data = attrs['value']
      del attrs['value']
    elif '_xml_attrs' in data:
      attrs = data['_xml_attrs']
      del data['_xml_attrs']
    if '_xml_name' in attrs:
      name = attrs['_xml_name']
      del attrs['_xml_name']

  if isinstance(data, dict):
    data = '\n'.join(sorted([to_xml(k, data[k], indent+' ') for k in data]))
    if data:
      data = '\n%s\n%s' % (data, indent)
  elif isinstance(data, list):
    ename = name[:-1] if (name[-1:] == 's') else 'item'
    data = '\n'.join([to_xml(ename, d, indent+' ') for d in data])
    if data:
      data = '\n%s\n%s' % (data, indent)
  else:
    data = xml_encode(data)

  if isinstance(attrs, dict):
    attrs = ' '.join(sorted([
      '%s="%s"' % (k, xml_encode(attrs[k])) for k in attrs]))

  if indent:
    fmt = indent + '<%s%s%s>%s</%s>'
  else:
    fmt = '<?xml version="1.0"?>\n<%s%s%s>%s</%s>\n'

  return fmt % (name, ' ' if attrs else '', attrs, data, name)


if False and (__name__ == '__main__'):
  print(to_xml('test', {
    '_xml_attrs': {'fancy': True, 'version': 1},
    'hello': 'world',
    '000': 'Zeroth Element',
    'elements': [1, 2, 3, 4]}))
