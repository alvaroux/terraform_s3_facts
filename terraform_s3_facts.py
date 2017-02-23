#!/usr/bin/python
# -*- coding: utf-8 -*-
DOCUMENTATION = '''
---
module: terrafrom_s3_facts
short_description: Gathers facts about remote terraform tfstate in s3 bucket
description:
    - Gathers facts about remote terraform tfstate in s3 bucket
version_added: "1.0"
options:
    bucket:
        description:
            - Name of the S3 bucket that stores the tfstate
        required: true
        default: ''
    object:
        description:
            - Path or key to the tfstate inside S3
        required: true
        default: ''
    version:
        description:
            - Version of the S3 Object
        required: false
        default: ''
    retries:
        description:
            - Number of retries
        required: false
        default: 0

author: "Alvaro Lopez <alvaroux@gmail.com>"
'''

EXAMPLES = '''
# Conditional example
- name: Gather terraform facts
  terraform_s3_facts:
    bucket: my_terraform_bucket
    object: my_folder/terraform.tfstate
  register: tf

- name: Conditional
  debug:
    msg: "This main vpc"
  when: tf.facts.terraform_vpc_id == "vpc-xxxxxxxx"
'''


from ansible.module_utils.six.moves.urllib.parse import urlparse
from ssl import SSLError

try:
    from boto.s3.connection import Location
    from boto.s3.connection import OrdinaryCallingFormat
    from boto.s3.connection import S3Connection
    from boto.s3.key import Key
    from boto.s3.acl import CannedACLStrings
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False


def key_check(module, s3, bucket, obj, version=None):
    try:
        bucket = s3.lookup(bucket)
        key_check = bucket.get_key(obj, version_id=version)
    except s3.provider.storage_response_error as e:
        if version is not None and e.status == 400:
            key_check = None
        else:
            module.fail_json(msg=str(e))
    if key_check:
        return True
    else:
        return False


def bucket_check(module, s3, bucket):
    try:
        result = s3.lookup(bucket)
    except s3.provider.storage_response_error as e:
        module.fail_json(msg=str(e))
    if result:
        return True
    else:
        return False


def read_s3file(module, s3, bucket, obj, retries, version=None):
    key = Key(s3.get_bucket(bucket))
    key.key = obj

    for x in range(0, retries + 1):
        try:
            content = key.get_contents_as_string()
            content = parse_terraform_outputs(content)
            module.exit_json(facts=content, changed=True)
        except s3.provider.storage_copy_error as e:
            module.fail_json(msg=str(e))
        except SSLError as e:
            if x >= retries:
                module.fail_json(msg="s3 download failed; %s" % e)
            pass


def fix_invalid_varnames(data):
    for (key, value) in data.items():
        if ':' in key or '-' in key:
            newkey = key.replace(':', '_').replace('-', '_')
            del data[key]
            data[newkey] = value

    return data


def parse_terraform_outputs(tfstate):
    outputs = {}
    prefix = 'terraform_'
    fields = json.loads(tfstate)
    modules = fields['modules']
    for module_list in modules:
        for key, value in module_list['outputs'].iteritems():
            outputs[prefix+key] = value['value']

    return fix_invalid_varnames(outputs)


def is_fakes3(s3_url):
    if s3_url is not None:
        return urlparse.urlparse(s3_url).scheme in ('fakes3', 'fakes3s')
    else:
        return False


def is_walrus(s3_url):
    if s3_url is not None:
        o = urlparse.urlparse(s3_url)
        return not o.hostname.endswith('amazonaws.com')
    else:
        return False


def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(dict(
            bucket=dict(required=True),
            object=dict(),
            version=dict(default=None),
            s3_url=dict(aliases=['S3_URL']),
            retries=dict(aliases=['retry'], type='int', default=0),
            rgw=dict(default='no', type='bool')
        ),
    )
    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=False)

    if not HAS_BOTO:
        module.fail_json(msg='boto required for this module')

    bucket = module.params.get('bucket')
    s3_url = module.params.get('s3_url')
    rgw = module.params.get('rgw')
    version = module.params.get('version')
    retries = module.params.get('retries')
    region, ec2_url, aws_connect_kwargs = get_aws_connection_info(module)

    if region in ('eu-east-1', '', None):
        location = Location.DEFAULT
    else:
        location = region

    if module.params.get('object'):
        obj = os.path.expanduser(module.params['object'])

    if not s3_url and 'S3_URL' in os.environ:
        s3_url = os.environ['S3_URL']

    if rgw and not s3_url:
        module.fail_json(msg='rgw flavour requires s3_url')

    if '.' in bucket:
        aws_connect_kwargs['calling_format'] = OrdinaryCallingFormat()

    try:
        if s3_url and rgw:
            rgw = urlparse.urlparse(s3_url)
            s3 = boto.connect_s3(
                is_secure=rgw.scheme == 'https',
                host=rgw.hostname,
                port=rgw.port,
                calling_format=OrdinaryCallingFormat(),
                **aws_connect_kwargs
            )
        elif is_fakes3(s3_url):
            fakes3 = urlparse.urlparse(s3_url)
            s3 = S3Connection(
                is_secure=fakes3.scheme == 'fakes3s',
                host=fakes3.hostname,
                port=fakes3.port,
                calling_format=OrdinaryCallingFormat(),
                **aws_connect_kwargs
            )
        elif is_walrus(s3_url):
            walrus = urlparse.urlparse(s3_url).hostname
            s3 = boto.connect_walrus(walrus, **aws_connect_kwargs)
        else:
            aws_connect_kwargs['is_secure'] = True
            try:
                s3 = connect_to_aws(boto.s3, location, **aws_connect_kwargs)
            except AnsibleAWSError:
                s3 = boto.connect_s3(**aws_connect_kwargs)

    except boto.exception.NoAuthHandlerFound as e:
        module.fail_json(msg='No Authentication Handler found: %s ' % str(e))
    except Exception as e:
        module.fail_json(msg='Failed to connect to S3: %s' % str(e))

    if s3 is None:
        module.fail_json(msg='Unknown error, failed to create s3 connection, no information from boto.')

    bucketrtn = bucket_check(module, s3, bucket)
    if bucketrtn is False:
        module.fail_json(msg="Source bucket cannot be found", failed=True)

    keyrtn = key_check(module, s3, bucket, obj, version=version)
    if keyrtn is False:
        if version is not None:
            module.fail_json(msg="Key %s with version id %s does not exist." % (obj, version), failed=True)
        else:
            module.fail_json(msg="Key %s does not exist." % obj, failed=True)

    read_s3file(module, s3, bucket, obj, retries, version=version)
    module.exit_json(failed=False)


# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

if __name__ == '__main__':
    main()
