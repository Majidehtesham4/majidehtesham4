### Iran ERP

Iranian localization for ERPNext: Jalali calendar, Iranian identifiers, fiscal year

### Installation

This app lives in the `erpnext-iran/apps/iran_erp` folder of its repository, so copy it into an
existing bench instead of using `bench get-app`:

```bash
cp -r erpnext-iran/apps/iran_erp $PATH_TO_YOUR_BENCH/apps/
cd $PATH_TO_YOUR_BENCH
bench setup requirements --python
ls -1 apps > sites/apps.txt
bench --site $SITE install-app iran_erp
bench build --app iran_erp
```

For a Docker based install see `erpnext-iran/README.md`.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/iran_erp
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
