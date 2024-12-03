"""Primary Controller"""

from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import NoResultFound
from flouria_models.exceptions.flouria_base import BadRequestError, NotFoundError
from flouria_api.response.messages import (
    UPDATE_SUCCESS,
    CREATE_SUCCESS,
    DUPLICATE,
    NOT_FOUND,
    ID_MISMATCH,
)

# pylint: disable=R0913, R0917, R0914, R1702, R0912, R1721


class PrimaryController:
    """Controller"""

    def __init__(
        self,
        repository,
        model,
        pydantic_model,
        # customer: str,
        account_id: str,
        sub_repos=None,
    ):
        self.repository = repository
        self.model = model
        # self.customer = customer
        self.account_id = account_id
        self.pydantic_model = pydantic_model
        self.sub_repos = sub_repos or {}

    def get_all(
        self,
        model_fields=None,
        skip: int = 0,
        limit: int = 100,
    ):
        """
        Fetches all model results, filtering those results if appropriate.
        If model_fields is set, it searhes for those additional models and
        adds that to the content returned for each result.
        """

        responses = []
        results = []
        results = self.repository.get_all(skip=skip, limit=limit)

        if not results:
            return results

        if model_fields:
            id_dicts = {f"{model}_ids": {} for model in model_fields}

            # Validate requested model fields against sub_repos
            valid_models = self.sub_repos.keys()
            invalid_models = model_fields - valid_models
            if invalid_models:
                raise ValueError(
                    f"Invalid model fields: {invalid_models}."
                    f"Valid options are: {valid_models}"
                )

            for result in results:
                result_data = {
                    key: value
                    for key, value in result.__dict__.items()
                    if not key.startswith("_")
                }

                for model in model_fields:

                    # Construct the ID field
                    id_field = f"{model}_id"
                    model_id = getattr(result, id_field, None)

                    # Fetch the associated model data if the ID is present
                    if model_id:
                        # if model_id in id_dicts dictionary, grab the value
                        if model_id in id_dicts[f"{id_field}s"][model_id]:
                            result_data[model] = id_dicts[f"{id_field}s"][model_id]
                        else:
                            # Fetch the repository for the model
                            repository_class = self.sub_repos[model]
                            model_result = repository_class.get_by_id(model_id)
                            if model_result:
                                result_data[model] = {
                                    key: value
                                    for key, value in model_result.__dict__.items()
                                }
                                # performs one search per id
                                id_dicts[f"{id_field}s"][model_id] = result_data[model]

                # Append the fully constructed resource
                responses.append(self.pydantic_model(**result_data))

            return responses

        return results

    def get_by_id(self, model_id, model_fields=None):
        """Fetches model by ID and returns the instance"""
        try:
            result = self.repository.get_by_id(model_id)
        except NoResultFound as e:
            raise NotFoundError(NOT_FOUND) from e
        if model_fields:
            # Validate requested model fields against sub_repos
            valid_models = self.sub_repos.keys()
            invalid_models = model_fields - valid_models
            if invalid_models:
                raise ValueError(
                    f"Invalid model fields: {invalid_models}."
                    f"Valid options are: {valid_models}"
                )

            result_data = {
                key: value
                for key, value in result.__dict__.items()
                if not key.startswith("_")
            }

            for model in model_fields:
                # Construct the ID field
                id_field = f"{model}_id"
                model_id = getattr(result, id_field, None)

                # Fetch the associated model data if the ID is present
                if model_id:
                    # Fetch the repository for the model
                    repository_class = self.sub_repos[model]
                    model_result = repository_class.get_by_id(model_id)

                    if model_result:
                        result_data[model] = {
                            key: value
                            for key, value in model_result.__dict__.items()
                            if not key.startswith("_")
                        }

            return self.pydantic_model(**result_data)

        return result

    def upsert(self, fields, request, model_fields=None):
        """Creates a new model instance or updates an existing instance"""

        if model_fields:
            for model in model_fields:

                # Construct the ID field
                id_field = f"{model}_id"
                model_id = getattr(request, id_field, None)

                repository_class = self.sub_repos[model]
                try:
                    repository_class.get_by_id(model_id)
                except NoResultFound as e:
                    error_msg = f"{model} with id: {model_id} not found"
                    raise NotFoundError(error_msg) from e

        attributes = {
            field: getattr(request, field)
            for field in fields
            if hasattr(request, field)
        }

        # Determine which fields have unqiue constraints
        unique_fields = []
        for constraint in self.model.__table__.constraints:
            if isinstance(constraint, UniqueConstraint):
                unique_fields.extend([col.name for col in constraint.columns])

        unique_attributes = {
            field: attributes[field] for field in fields if field in unique_fields
        }

        if getattr(request, "id", None) is not None:
            id_value = getattr(request, "id")
            try:
                result = self.repository.get_by_id(id_value)
            except NoResultFound as e:
                raise NotFoundError(NOT_FOUND) from e

            attributes.pop("id", None)
            unique_attributes.pop("id", None)
            if unique_attributes:
                results = self.repository.search_by_fields(unique_attributes)
                for result in results:
                    if result.id != id_value:
                        raise BadRequestError(DUPLICATE)

            # add updated_by
            if "updated_by" in self.model.__table__.columns:
                attributes["updated_by"] = self.account_id

            self.repository.update(id_value, attributes)
            return UPDATE_SUCCESS

        # check to see if instance already exists
        if unique_attributes:
            result = self.repository.search_by_fields(unique_attributes)
            if result:
                # instance already exists
                raise BadRequestError(DUPLICATE)

        # add updated_by and created_by
        if "created_by" in self.model.__table__.columns:
            attributes["created_by"] = self.account_id
        if "updated_by" in self.model.__table__.columns:
            attributes["updated_by"] = self.account_id

        # if model doesn't exist, create it
        self.repository.create(attributes)
        return CREATE_SUCCESS

    def update(self, id_value, fields, request, model_fields=None):
        """Updates an existing model instance"""
        if model_fields:
            for model in model_fields:

                # Construct the ID field
                id_field = f"{model}_id"
                model_id = getattr(request, id_field, None)

                repository_class = self.sub_repos[model]
                try:
                    repository_class.get_by_id(model_id)
                except NoResultFound as e:
                    error_msg = f"{model} with id: {model_id} no found"
                    raise NotFoundError(error_msg) from e

        if getattr(request, "id", None) is not None:
            given_id = getattr(request, "id")
            if given_id != int(id_value):
                raise BadRequestError(ID_MISMATCH)

        attributes = {field: getattr(request, field) for field in fields}

        # add updated_by
        if "updated_by" in self.model.__table__.columns:
            attributes["updated_by"] = self.account_id
        if attributes.get("id") is None:
            attributes["id"] = id_value
        # update the existing model by its ID
        self.repository.update(id_value, attributes)
        return UPDATE_SUCCESS

    def delete(self, model_id):
        """Deletes model instance by ID"""
        if model_id:
            try:
                model = self.repository.get_by_id(model_id)
            except NoResultFound as e:
                raise NotFoundError(NOT_FOUND) from e

            # if model instance is found, delete it
            self.repository.delete(model)
