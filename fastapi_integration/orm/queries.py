from sqlalchemy import (
    select,
    delete as sqla_delete,
    update as sqla_update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Type, Union, Tuple, Any
from sqlalchemy import func
from sqlalchemy.orm import RelationshipProperty
from .signals import SignalMixin
from .base import BaseQuery



class QueryMixin(BaseQuery, SignalMixin):
    async def apply_filter_type(self, filter_type: str, conditions: list, column, value) -> list:
        conditions.append(self.condition_map.get(filter_type, lambda column, value: column == value)(column, value))
        return conditions


    def _apply_ordering(self, stmt, order_by: Union[str, Tuple[str]]) -> None:
        """
        Apply ordering to the SQL statement based on the given order_by parameter.

        :param stmt: The SQL statement to modify.
        :param order_by: A string or tuple of strings indicating the columns to order by.
        :return: None
        """
        stmt = stmt.order_by(*[getattr(self.cls, col.lstrip("-")).desc() if col.startswith("-") else getattr(self.cls, col).asc() for col in (order_by if isinstance(order_by, tuple) else (order_by,))])
        return stmt


    

    async def get(self, db_session: AsyncSession, joins=set(), order_by=None, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        stmt = await self.build_handler(db_session, joins=joins, order_by=order_by, **kwargs)
        result = await db_session.execute(stmt)
        self.instance = result.scalars().first()
        return self.instance


    async def filter(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0, limit: int = 20, get_count=False, 
                    values_fields:list = [], where=None, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        stmt = await self.build_handler(db_session, joins=joins, order_by=order_by, skip=skip, limit=limit, where=where, **kwargs)

        if values_fields:
            stmt = stmt.with_only_columns(*[getattr(self.cls, field) for field in values_fields])


        result = await db_session.execute(stmt)
        if self.needs_scalar:
            self.instance = result.scalars().all()
        else:
            self.instance = result.all()

        if not get_count:
            return self.instance

        else:
            stmt = await self.build_handler(db_session, joins=joins, order_by=order_by, **kwargs)
            count = await self.count(db_session, stmt)
            return (self.instance, count)




    async def count(self, db_session: AsyncSession, stmt) -> int:
        stmt = stmt.with_only_columns(func.count(self.cls.id))
        result = await db_session.execute(stmt)
        return result.scalar()


    async def create(self, db_session: AsyncSession, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        self.instance = self.cls()
        for key, value in kwargs.items():
            attr = getattr(self.cls, key, None)

            if attr is None:
                raise ValueError(f"Attribute '{key}' not found in class '{self.cls.__name__}'")
            if hasattr(attr, "property") and isinstance(attr.property, RelationshipProperty):
                related_instance = value
                setattr(self.instance, key, related_instance)
            else:
                setattr(self.instance, key, value)

        # instance = await self._pre_save(db_session, instance, **kwargs)
        try:
            db_session.add(self.instance)
            await db_session.flush()
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            raise e
        return self.instance



    async def all(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0, limit: int = 20, get_count=False) -> Union[Type[Any], Type["QueryMixin"]]:
        return await self.filter(db_session, joins, order_by=None, skip=0, limit=None)
    

    async def delete(self, db_session: AsyncSession, joins=set(), **kwargs) -> int:
        """
        Delete instances matching the given filters.
        :param db_session: The async database session.
        :param kwargs: Filters for the instances to delete.
        :return: None
        """
        stmt = await self.build_handler(db_session=db_session, joins=joins, **kwargs)
        stmt = await self._pre_delete(db_session, stmt, **kwargs)
        delete_stmt = sqla_delete(self.cls).where(stmt.whereclause)
        result = await db_session.execute(delete_stmt)
        await db_session.commit()
        return result.rowcount


    async def update(self, db_session: AsyncSession, data: dict, joins=set(), **kwargs) -> int:
        """
        Update instances matching the given filters with the given data.

        :param db_session: The async database session.
        :param update_data: A dictionary containing the data to update.
        :param kwargs: Filters for the instances to update.
        :return: None
        """
        stmt = await self.build_handler(db_session=db_session, joins=joins, **kwargs)
        stmt = await self._pre_update(db_session, stmt, **kwargs)
        update_stmt = sqla_update(self.cls).where(stmt.whereclause).values(data)
        result = await db_session.execute(update_stmt)
        await db_session.commit()
        if result.rowcount == 1:
            updated_instance = await self.get(db_session, **kwargs)
            return updated_instance
        else:
            return result.rowcount or None
    

    async def aggregate(self, db_session: AsyncSession, field: str, agg_func: str = "sum", joins=set(), **kwargs) -> Union[int, float, None]:
        """
        Perform an aggregation on a column.

        :param db_session: The async database session.
        :param aggregation_fn: The aggregation function to use.
        :param column: The column to aggregate.
        :param kwargs: Additional filters for the query.
        :return: The result of the aggregation.
        """
        supported_agg_funcs = {
            "sum": func.sum,
            "count": func.count,
            "avg": func.avg,
            "min": func.min,
            "max": func.max
        }
        if agg_func.lower() not in supported_agg_funcs:
            raise NotImplementedError(f"Unsupported aggregation function '{agg_func}'")
        
        aggregation = supported_agg_funcs[agg_func.lower()](getattr(self.cls, field))
        stmt = select(aggregation)

        stmt = await self.build_handler(db_session, joins=joins, **kwargs)
        stmt = stmt.select_from(self.cls).with_only_columns(aggregation)
        result = await db_session.execute(stmt)
        return result.scalar()
        

    

    async def exclude(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0,  get_count=False, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        """
        Retrieve instances that do not match the given filters.

        :param db_session: The async database session.
        :param joins: A set of join conditions.
        :param order_by: A string or tuple of strings indicating the columns to order by.
        :param skip: The number of instances to skip.
        :param limit: The maximum number of instances to return.
        :param get_count: If True, also return the count of instances.
        :param kwargs: Additional filters for the query.
        :return: A list of instances or a tuple containing the list of instances and the count.
        """
        all_stmt = await self.build_handler(db_session=db_session, joins=joins, order_by=order_by, skip=skip, limit=None)
        all_result = await db_session.execute(all_stmt)
        all_instances = all_result.scalars().all()
        exclude_stmt = await self.build_handler(db_session=db_session, joins=joins, order_by=order_by, skip=skip, limit=None, **kwargs)    
        exclude_result = await db_session.execute(exclude_stmt)
        exclude_instances = exclude_result.scalars().all()
        self.instance = list(set(all_instances) - set(exclude_instances))
        if not get_count:
            return self.instance
        else:
            count = len(self.instance)
            return (self.instance, count)




    async def add_m2m(self, db_session: AsyncSession, other_model) -> None:
        """
        Add a many-to-many relationship between two entities.d
        :param db_session: The async database session.
        :param other_model: The entity in the relationship.
        :return: None
        """
        if self.instance is None:
            raise ValueError("Perform a query before using add_m2m method")
        for attr, value in self.instance.__class__.__dict__.items():
            if isinstance(value, RelationshipProperty) and value.argument == other_model.__class__.__name__:
                getattr(self.instance, attr).append(other_model)
        for attr, value in other_model.__class__.__dict__.items():
            if isinstance(value, RelationshipProperty) and value.argument == self.instance.__class__.__name__:
                getattr(other_model, attr).append(self.instance)

        await db_session.commit()




    def _apply_distinct(self, stmt, distinct_fields=None):
        """
        Apply a DISTINCT clause to the SQL statement.

        :param stmt: The SQL statement to modify.
        :return: None
        """

        if distinct_fields is not None:
            if isinstance(distinct_fields, (list, tuple)):
                columns = [getattr(self.cls, field) for field in distinct_fields]
                stmt = stmt.distinct(*columns)
            else:
                raise ValueError("distinct_fields should be a list or tuple of field names.")
        return stmt



    async def get_or_create(self, db_session: AsyncSession, create_data: dict, **kwargs) -> Tuple[Union[Type[Any], Type["QueryMixin"]], bool]:
        """
        Retrieve an instance if it exists, otherwise create a new one with the given data.

        :param db_session: The async database session.
        :param create_data: A dictionary containing the data for the new instance.
        :param kwargs: Filters for the query.
        :return: A tuple containing the instance and a boolean indicating if the instance was created.
        """
        instance = await self.get(db_session, **kwargs)
        created = False
        if not instance:
            instance = await self.create(db_session, **create_data)
            created = True
        return instance, created