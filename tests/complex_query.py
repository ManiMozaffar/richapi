import sys, os
current_dir = os.path.abspath('.')
sys.path.insert(0, current_dir)

from sqlalchemy.orm import declarative_base
from fastapi_integration.db import Engine
from fastapi_integration.models import AbstractBaseUser
from tests.start import MyConfig
import random, string, unittest
from fastapi_integration.models import AbstractModel
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy import func, any_
from sqlalchemy.sql.expression import select


class TestQueryMixin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await db_engine.create_database(Base)
        async with db_engine.get_pg_db_with_async() as session:
            pass

            
    async def asyncTearDown(self):                     
        async with db_engine.engine.connect() as conn:
            await conn.close()
            await db_engine.engine.dispose()
        

    async def test_where_and_join_and_selects(self):        
        async with db_engine.get_pg_db_with_async() as session:
            random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            model1 = Model1(name=f"{random_chars}")
            model2 = Model2(name=f"{random_chars}_part2")
            model1.model2s.append(model2)
            session.add(model1)
            session.add(model2)
            await session.commit()

            ## My way
            query = await Model1.objects.filter(
                session,
                limit=20,
                select_models=[Model2,],
                where=( 
                    (Model1.name + Model2.name).contains(f"{random_chars}"), 
                ),
                joins=[Model1.id == Model2.id],
                order_by="name",
                id__gte=0
            )


            ## SQLAlchemy Way
            query2 = select(
                Model1, Model2
            ).select_from(
                Model1
            ).join(
                Model2, Model1.id == Model2.id
            ).where(
                (Model1.name + Model2.name).contains(random_chars) &
                (Model1.id >= 0)
            ).limit(
                20
            )
            items2 = await session.execute(query2)
            results = items2.all()
            

            self.assertEqual(results[0][0].id, query[0][0].id)
            self.assertEqual(results[0][1].id, query[0][1].id)
        




if __name__ == "__main__":
    Base = declarative_base()
    association_table = Table(
        'association', Base.metadata,
        Column('model1_id', Integer, ForeignKey('model1.id')),
        Column('model2_id', Integer, ForeignKey('model2.id'))
    )


    class Model1(AbstractModel, Base):
        __tablename__ = 'model1'
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), unique=True, index=True)

        model2s = relationship("Model2", secondary=association_table, back_populates="model1s")


    class Model2(AbstractModel, Base):
        __tablename__ = 'model2'
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), unique=True, index=True)

        model1s = relationship("Model1", secondary=association_table, back_populates="model2s")



    db_engine = Engine(MyConfig())
    unittest.main()