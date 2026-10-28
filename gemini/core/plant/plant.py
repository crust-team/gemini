"""Plant container that holds units, database, and project configuration."""


class Plant:
    """Includes units (assets), connects them, and manages database access."""

    def __init__(self):
        """Initialize plant."""
        self.project_path = None
        self.name = None
        self.parameters = dict()
        self.units = []
        self.databases = dict()
        self.diagram = None

    def update_parameters(self, parameters):
        """Update plant parameters."""
        self.parameters.update(parameters)

    def add_unit(self, unit):
        """Add asset instance to the plant."""
        self.units.append(unit)

    def remove_unit(self, unit_id):
        """Remove asset instance based on unit id.

        :param str unit_id: the unique identifier of an asset.
        """
        for ii, unit in enumerate(self.units):
            if unit.id == unit_id:
                del self.units[ii]
                break

    def get_unit(self, unit_id):
        """Get asset instance based on unit id.

        :param str unit_id: the unique identifier of an asset.
        """
        return next((unit for unit in self.units if unit.id == unit_id), None)

    def connect_unit(self):
        """Connect all units."""
        for cell in self.diagram["cells"]:
            if cell["type"] == "devs.Link":
                source_unit = self.get_unit(cell["source"]["id"])
                target_unit = self.get_unit(cell["target"]["id"])
                if source_unit is not None and target_unit is not None:
                    source_unit.to_units.append(target_unit)
                    target_unit.from_units.append(source_unit)

    def link_unit(self):
        """Link all unit modules."""
        for unit in self.units:
            unit.link()

    def add_database(self, database, category):
        """Add database to plant."""
        database.update_parameters(self.parameters["database"])

        if category in self.databases:
            self.databases[category].append(database)
        else:
            self.databases[category] = [database]

    @property
    def database(self):
        """Return the primary "measured" database reader.

        Convenience accessor for callers that expect a single database
        connection. When more than one reader is registered for the
        "measured" category (e.g. a CSV reader plus an external historian
        reader), the most recently added one takes precedence.
        """
        measured = self.databases.get("measured")

        return measured[-1] if measured else None

    def connect_database(self):
        """Connect to database."""
        for category, databases in self.databases.items():
            for database in databases:
                database.connect()

    def register_tags(self):
        """Register tags with database."""
        for category, databases in self.databases.items():
            for database in databases:
                database.register_tags(self.units)

    def find_modules(self, category):
        """Find modules of specified category."""
        modules = []
        for unit in self.units:
            modules.extend(unit.modules[category])

        return modules
