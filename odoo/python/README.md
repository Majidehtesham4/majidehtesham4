Python libraries some OCA modules need and Odoo's image lacks, given to Odoo through PYTHONPATH
(docker-compose.yml mounts this folder at /mnt/python):

- `cssselect` 1.6.0 (BSD-3-Clause, see cssselect/LICENSE), for `resource_booking` (appointments).
