import sys, os
current_dir = os.path.abspath('.')
sys.path.insert(0, current_dir)

from sqlalchemy.orm import declarative_base
from fastapi_integration.db import Engine
from tests.start import MyConfig
import random, string, unittest
from fastapi_integration.models import AbstractModel
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy import text
import time
from sqlalchemy import select

class TestQueryMixin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await db_engine.create_database(Base)
        async with db_engine.get_pg_db_with_async() as session:
            pass

            
    async def asyncTearDown(self):                     
        async with db_engine.engine.connect() as conn:
            await conn.close()
            await db_engine.engine.dispose()
    

    async def test_double_underline_notation_and_perfomance(self):  

        start_time = time.time()    
        async with db_engine.get_pg_db_with_async() as session:
            random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            model1 = Model1(name=random_chars)
            session.add(model1)
            await session.flush()
            model3 = Model3(model1=model1)
            session.add(model3)
            await session.flush()
            stmt = select(Model3).join(Model1).filter(Model1.name == random_chars)
            result = await session.execute(stmt)
            query = result.scalars().all()
            await session.delete(model3)
            await session.delete(model1)
            await session.commit()


        elapsed_time = time.time() - start_time
        start_time = time.time()    


        async with db_engine.get_pg_db_with_async() as session:
            random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=6))  
            model1 = await Model1.objects.create(session, name=random_chars)  
            await Model3.objects.create(session, model1=model1)
            query = await Model3.objects.filter(session, model1__name=random_chars)
            await Model3.objects.delete(session, model1_id=model1.id)
            await Model1.objects.delete(session, name=random_chars)
        elapsed_time2 = time.time() - start_time


        self.assertEqual(len(query), 1)
        self.assertGreater(elapsed_time, elapsed_time2)
        



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
        model3s = relationship("Model3", back_populates="model1")



    class Model2(AbstractModel, Base):
        __tablename__ = 'model2'
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), unique=True, index=True)

        model1s = relationship("Model1", secondary=association_table, back_populates="model2s")
    


    class Model3(AbstractModel, Base):
        __tablename__ = 'model3'
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), unique=True, index=True)
        model1_id = Column(Integer, ForeignKey('model1.id'))
        model1 = relationship("Model1", back_populates="model3s")




    db_engine = Engine(MyConfig())
    unittest.main()