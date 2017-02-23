# terraform_s3_facts
Ansible module that takes outputs from terraform tfstate and set usable facts by Ansible

# Description
Gathers facts about remote terraform tfstate in s3 bucket at the moment

# Usage
##### Install
create a folder called `library` in the same path where your playbooks are,
 and put this project inside
##### Declare a new task in your Ansible role and register the results
```
- name: Get terraform facts
  terraform_s3_facts:
    bucket: my_terraform_bucket
    object: my_folder/terraform.tfstate
  register: tf
```
Once you have registered the output you can use this vars in other tasks, templates, etc

```
- name: debug
  debug:
    var: tf
```
This outputs all your terraform outputs like:
```
ok: [localhost] => {
    "tf": {
        "changed": true,
        "facts": {
            "terraform_rds_address": "my_rds.xxxxxxxxxx.eu-west-1.rds.amazonaws.com",
            "terraform_rds_endpoint": "my_rds.xxxxxxxxxx.eu-west-1.rds.amazonaws.com:5432",
            "terraform_rds_id": "my_rds",
            "terraform_vpc_cidr": "10.x.x.x/18",
            "terraform_vpc_id": "vpc-xxxxxxxx"
        }
    }
}

```

Now you can use the `tf` object and access its contents `tf.facts.terraform_rds_endpoint`

Note that all the terraform outputs are prefixed by **'terraform_'**.
The module also change score named variables by underscore in order to make variable names compatible with Ansible,
for example a terraform output named `vpc-id` will be renamed to: `terraform_vpc_id`

##### More exmaples
```
- name: Conditional
  debug:
    msg: "This is main vpc"
  when: tf.facts.terraform_vpc_id == "vpc-xxxxxxxx"

- name: Mount NFS Folders
  mount:
    name: /mnt/foo
    src: "{{ansible_ec2_placement_availability_zone}}.{{ tf.facts.terraform_foo_efs_dnsname | regex_replace('([a-z0-9|-]+)\\.(.*)$','\\2') }}:/"
    fstype: nfs
    opts: defaults,hard,nfsvers=4.1,retrans=2,timeo=600,rsize=1048576,wsize=1048576,noatime,lookupcache=positive
    state: mounted
```

