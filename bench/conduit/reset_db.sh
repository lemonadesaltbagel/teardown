#!/bin/sh
# Restore the pristine database inside the API container (same inode, between requests). Renaming a new file into
# the bind mount from the host races with the VM's file sharing; an in-container overwrite does not.
exec docker exec teardown-conduit-api sh -c 'cat /data/pristine.sqlite3 > /data/db.sqlite3 && rm -f /data/db.sqlite3-journal'
