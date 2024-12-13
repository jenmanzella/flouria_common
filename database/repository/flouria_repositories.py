"""Repository functions for Flouria table models"""

from datetime import datetime
from typing import Any, TypeVar, Generic, Type, List, Optional, Union, Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, select, Date

from flouria_models.personal_table_models import (
    User,
    Accounts,
    AddictionManagement,
    Journal,
    WritingEntry,
    Prompt,
    Contacts,
    DateEntry,
    Health,
    Points,
    TaskList,
    Memories,
    Goal,
    Rule,
    RuleReports,
    ConnectToBody,
)

# pylint: disable= R0914, R0903, R0913, R0917

MODELTYPE = TypeVar("MODELTYPE")


class BaseRepository(Generic[MODELTYPE]):
    """This repository provides general functionality for multiple tables"""

    def __init__(
        self,
        model: Type[MODELTYPE],
        db: Session,
    ):
        """Initializes the BaseRepository class attributes"""
        self.db = db
        self.model: Type[MODELTYPE] = model

    def get_by_id(self, model_id: int) -> Optional[MODELTYPE]:
        """Gets the table instance by the ID provided"""
        query = select(self.model)
        query = query.where(self.model.id == model_id)
        result = self.db.execute(query).scalars().first()
        return result

    def get_all(self) -> List[MODELTYPE]:
        """Gets all instances of the table model"""
        return self.db.query(self.model).all()

    def delete_by_id(self, model_id: int) -> None:
        """Deletes a model instance by the ID provided"""
        # Construct the delete query
        query = delete(self.model).where(self.model.id == model_id)

        # Execute the delete query
        self.db.execute(query)
        self.db.commit()

    def create(self, attributes: Optional[Dict[str, Any]] = None) -> MODELTYPE:
        """
        Creates a new instance of the table model using the attributes provided
        """
        attributes = attributes or {}
        model = self.model(**attributes)
        try:
            self.db.add(model)
            self.db.commit()
            self.db.refresh(model)
            return model
        except IntegrityError:
            # Rollback if error occurs
            self.db.rollback()
            # Optionally log the exception
            raise

    def search_by_fields(
        self, filters: Optional[dict[str, Any]] = None
    ) -> List[MODELTYPE]:
        """
        Search for records in the database using a dictionary of multiple
        fields and their values.
        """
        filters = filters or {}
        query = select(self.model)

        for field, value in filters.items():
            query = query.where(getattr(self.model, field) == value)

        results = self.db.execute(query).scalars().all()
        return results

    def search_by(self, field, value):
        """
        Search for records in the database using one field and it's value
        This does not execute the query
        """
        query = select(self.model)
        query = query.where(getattr(self.model, field) == value)
        return query

    def update(self, model_id: int, update_data: dict) -> MODELTYPE:
        """
        Updates a model by ID. Only the fields provided in update_data will be updated.
        """
        # Retrieve the model instance by ID
        model = self.get_by_id(model_id)

        if not model:
            raise ValueError(f"Model with ID {model_id} not found.")

        # Update only the fields provided in update_data
        for field, value in update_data.items():
            if hasattr(model, field):
                setattr(model, field, value)

        # Add and commit the changes to the database
        self.db.add(model)
        self.db.commit()

        # Optionally refresh the model instance to get the latest state
        self.db.refresh(model)

        return model

    def get_by_date(self, selected_date) -> Optional[Union[MODELTYPE, List[MODELTYPE]]]:
        """
        Retrieves one or multiple instances where date matches the
        date provided (str or Date type).
        Returns: a list of instances
        Remember to check list length and grab element 0
        when I am only expecting one instance per date.
        """
        # If selected_date is a string, convert it to Date format
        if isinstance(selected_date, str):
            selected_date = datetime.strptime(selected_date, "%Y-%m-%d").date()

        # Construct the query to match the date
        query = select(self.model).where(self.model.date == selected_date)

        # Execute the query
        results = self.db.execute(query).scalars().all()

        return results

    def add_all_jsonb(
        self,
        jsonb_fields,
        normal_fields,
        selected_date: Date,
        update_data: dict,
        list_in_dict=False,
    ):
        """
        If a field is provided in update_data, existing content is updated.
        If a field is excluded, existing content is retained.
        If no record exists for the given date, fetch the most recent previous record
        and use its data to create a new instance for the provided date.
        """

        # Step 1: Get the existing record by the selected date
        existing_record = self.get_by_date(selected_date)

        if not existing_record:
            # No record found for the selected date, find the most recent previous record
            previous_record = (
                self.db.query(self.model)
                .filter(self.model.date < selected_date)
                .order_by(self.model.date.desc())
                .first()
            )

            if not previous_record:
                # add selected_date (usually current date) to update_data
                update_data["date"] = selected_date
                new_record = self.create(update_data)
                return new_record

            # Use the previous record's data to create a new record for the selected date
            new_record_data = {
                field: getattr(previous_record, field, None)
                for field in self.model.__table__.columns.keys()
            }
            new_record_data["date"] = selected_date  # Set the new date

            # Add the new record to the database
            new_record = self.model(**new_record_data)
            self.db.add(new_record)
            self.db.commit()

            existing_record = (
                new_record  # Now treat this new record as the existing one
            )

        model_id = existing_record.id

        # Create a new dictionary to store updated values
        new_values = {}
        new_values["date"] = selected_date

        # Iterate over all fields in the model
        for field in self.model.__table__.columns.keys():
            # For JSONB fields, merge the new data with the existing data
            if field in jsonb_fields:
                # Get the current JSONB data from the existing record
                existing_jsonb_data = getattr(existing_record, field, None)

                # Update the JSONB data by merging it with the new data
                new_jsonb_data = update_data.get(field, {})

                # if the key_name is the same, update data will
                # overwrite the previous value associated with that key_name
                if list_in_dict:
                    old_list = existing_jsonb_data[field]
                    new_list = new_jsonb_data[field]
                    combined_list = list(set(old_list + new_list))
                    merged_jsonb_data = {field: combined_list}

                else:
                    merged_jsonb_data = {**existing_jsonb_data, **new_jsonb_data}

                # Set the merged data in the new_values dictionary
                new_values[field] = merged_jsonb_data

            # For normal fields, update only if the field is in update_data
            elif field in normal_fields:
                if field in update_data:
                    new_values[field] = update_data[field]
                else:
                    # Retain the existing value if not in update_data
                    new_values[field] = getattr(existing_record, field, None)

        # Update the record with new_values
        update_results = self.update(model_id, new_values)
        return update_results

    def get_jsonb_field(self, model_id, field_name):
        """Returns all JSON content for a particular model_id and field"""
        model_instance = self.search_by("id", model_id)
        if not model_instance:
            return None
        return getattr(model_instance, field_name, None)

    def delete_by_key(self, model_id, field_name, key_name):
        """Deletes key by its name within a particular JSONB field"""
        model_instance = self.search_by("id", model_id)
        if field_name in self.model.__table__.columns.keys():
            field_value = getattr(model_instance, field_name, None)
            if key_name in field_value:
                del field_value[key_name]
                setattr(model_instance, field_name, field_value)
                self.db.add(model_instance)
                self.db.commit()
            else:
                raise KeyError(f"'{key_name}' not found in field")
        else:
            raise ValueError(f"'{field_name}' not found in table")

        return model_instance


class UserRepository(BaseRepository[User]):
    """User Repository"""


class DateEntryRepository(BaseRepository[DateEntry]):
    """DateEntry Repository"""


class HealthRepository(BaseRepository[Health]):
    """Health Repository"""


class AddictionManagementRepository(BaseRepository[AddictionManagement]):
    """Adderall Repository"""

    def add_new_content(self, date, update_data):
        """Appends all new content in update_data"""
        jsonb_fields = {
            "triggers",
            "messages",
            "alternatives",
            "short_term_effects",
            "long_term_risks",
            "recovery_rewards",
        }
        normal_fields = {
            "max_dose",
            "med_count",
            "overused",
            "substance",
            "prior_sleep",
        }
        self.add_all_jsonb(
            jsonb_fields, normal_fields, date, update_data, list_in_dict=True
        )


class JournalRepository(BaseRepository[Journal]):
    """Journal Repository"""

class WritingEntryRepository(BaseRepository[WritingEntry]):
    """Writing Entry Repository"""


class PromptRepository(BaseRepository[Prompt]):
    """Prompt Repository"""


class PointsRepository(BaseRepository[Points]):
    """Points Repository"""


class ContactsRepository(BaseRepository[Contacts]):
    """Contacts Repository"""


class TaskListRepository(BaseRepository[TaskList]):
    """TaskList Repository"""

    def add_new_content(self, date, update_data):
        """Adds new task content"""
        jsonb_fields = {"task_list"}
        normal_fields = {"date"}
        self.add_all_jsonb(jsonb_fields, normal_fields, date, update_data)


class AccountsRepository(BaseRepository[Accounts]):
    """Accounts Repository"""

    def add_new_content(self, date, update_data):
        """Updates account balances"""
        jsonb_fields = {"account_balances"}
        normal_fields = {"date", "summary"}
        self.add_all_jsonb(jsonb_fields, normal_fields, date, update_data)


class MemoriesRepository(BaseRepository[Memories]):
    """
    Memories Repository. We don't need to call add_all_json, since we allow
    multiple entries within one day that append existing content.
    """

    def add_tag(self, model_id, person_id):
        """Adds a photo tag for a particular memory entry"""
        model_object = self.get_by_id(model_id)
        tags = getattr(model_object, "tags")
        if person_id not in tags["people"]:
            tags["people"].append(person_id)
            setattr(model_object, "tags", tags)
            self.db.add(model_object)
            self.db.commit()

    def remove_tag(self, model_id, person_id):
        """Removes a photo tag for a particular memory entry"""
        model_object = self.get_by_id(model_id)
        tags = getattr(model_object, "tags")
        if person_id in tags["people"]:
            tags["people"].remove(person_id)
            setattr(model_object, "tags", tags)
            self.db.add(model_object)
            self.db.commit()


class GoalRepository(BaseRepository[Goal]):
    """Goal Repository"""


class RuleRepository(BaseRepository[Rule]):
    """Rules Repository"""


class RuleReportsRepository(BaseRepository[RuleReports]):
    """RuleReports Repository"""

    def add_new_content(self, date, update_data):
        """Updates account balances"""
        jsonb_fields = {"rules_followed"}
        normal_fields = {"date"}
        self.add_all_jsonb(jsonb_fields, normal_fields, date, update_data)


class ConnectToBodyRepository(BaseRepository[ConnectToBody]):
    """ConnectToBody Repository"""
