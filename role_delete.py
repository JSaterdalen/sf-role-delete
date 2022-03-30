#! /usr/bin/env python3

import os
import subprocess
import pandas as pd
from bs4 import BeautifulSoup

FILE_DIR = "_roleDelete"
ROLES_DIR = f"{FILE_DIR}/force-app/main/default/roles"
USER_UPSERT = f'sfdx force:data:bulk:upsert -s User -f users_update.csv -i Id -w 4'
SOQL_QUERY = (f'sfdx force:data:soql:query '
              f'-q "SELECT Id, UserRoleId FROM User WHERE UserRoleId != null" '
              f'-r csv > users.csv')
DESTRUCT_CMD = f'sfdx force:mdapi:deploy -d destructiveChanges -w 5 --verbose'


def cmd(command: str, sfdx: bool):
    # run a given bash command
    # if sfdx = true, run in sfdx project folder
    if sfdx:
        subprocess.run([f'cd {FILE_DIR} && {command}'], shell=True)
    else:
        subprocess.run([command], shell=True)


def unassign_roles():
    # query users who have roles
    cmd(SOQL_QUERY, True)

    if os.stat("_roleDelete/users.csv").st_size == 1:
        return

    df = pd.read_csv('_roleDelete/users.csv')
    df['UserRoleId'] = "#N/A"
    df.to_csv('_roleDelete/users_update.csv', index=False)

    cmd(USER_UPSERT, True)


def make_package(del_list: list):
    # create folder structure
    os.makedirs('_roleDelete/destructiveChanges', exist_ok=True)

    # package.xml starter
    package = """
    <Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <version>54.0</version>
    </Package>
    """
    # with open(package) as f:
    soup = BeautifulSoup(package, 'xml')

    # create blank package.xml
    with open("_roleDelete/destructiveChanges/package.xml", "w") as f:
        f.write(str(soup))

    # include metadata to delete
    types_tag = soup.new_tag('types')
    name_tag = soup.new_tag('name')
    name_tag.string = 'Role'

    for item in del_list:
        member_tag = soup.new_tag('members')
        member_tag.string = item
        types_tag.append(member_tag)

    types_tag.append(name_tag)
    soup.Package.append(types_tag)

    # save changes to destructiveChanges.xml
    with open("_roleDelete/destructiveChanges/destructiveChanges.xml", "w") as f:
        f.write(str(soup))


def parse_roles():
    # build dict of roles and their parents

    # get files in roles folder
    role_files = os.listdir(ROLES_DIR)

    roles = {}
    for rf in role_files:
        with open(f'{ROLES_DIR}/{rf}') as f:
            soup = BeautifulSoup(f, 'xml')

        parent_role = soup.find('parentRole')
        role_name = rf.replace(".role-meta.xml", "")

        if parent_role:
            roles[role_name] = parent_role.string
        else:
            roles[role_name] = None

    return roles


def delete_child_roles(roles: dict):
    # find roles who are not parents
    del_list = []

    for rf in roles.keys():
        if rf not in roles.values():
            del_list.append(rf)

    # dl = len(del_list)
    # print(f'delete list ({dl}): ')
    # print(del_list)
    # print('\n')

    make_package(del_list)

    # delete roles from org
    cmd(DESTRUCT_CMD, True)

    # remove deleted from roles
    for k in del_list:
        roles.pop(k)

    # rl = len(roles)
    # print(f'next roles ({rl}): ')
    # print(roles)
    # print('\n')


# select org
ORG = input("Which org should this be run against?: ")

# create temporary sfdx project
cmd(f'sfdx force:project:create -n {FILE_DIR}', False)
cmd(f'sfdx config:set defaultusername={ORG}', True)

# unassign all users from roles
unassign_roles()

# pull role metadata
cmd('sfdx force:source:retrieve -m "Role"', True)

# map roles to their parents
roles = parse_roles()

# while roles exists, build a destructiveChanges.xml and delete one level of roles at a time
while roles:
    delete_child_roles(roles)

# # clean up files
cmd(f'rm -rf {FILE_DIR}', False)
