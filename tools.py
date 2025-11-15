from fastmcp import FastMCP
from sqlalchemy.orm import sessionmaker
from DBConnection import ExpensiveTracker, engine  
from sqlalchemy import String,cast
from DBConnection import init_database
from datetime import datetime

# Initialize MCP app
mcp = FastMCP(name="ExpensiveTracker")

# Create a session factory
Session = sessionmaker(bind=engine)

@mcp.tool(name="add_expense", description="Add a new monthly expense record to the database.")
def InsertItem(
    date: str,
    education: int,
    travel: int,
    food: int,
    fruit: int,
    medicine: int,
    friends: int,
    description: str = ""
):
    """Add a new expense record into the database."""
    session = Session()
    try:
        new_record = ExpensiveTracker(
            date=date,
            education=education,
            travel=travel,
            food=food,
            fruit=fruit,
            medicine=medicine,
            friends=friends,
            description=description,
            created_at=datetime.now()
        )
        session.add(new_record)
        session.commit() # permanently save them in the database
        return {"status": "success", "message": "Expense added successfully."}
    except Exception as e:
        session.rollback() 
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


@mcp.tool(name="get_expenses_record", description="Fetch expense data by month or specific category.")
def get_expenses_record(month: str = None, category: str = None):
    """
    Fetch records from ExpensiveTracker table.
    You can filter by month (YYYY-MM) or get total for a specific category
    (e.g. 'food', 'education', 'medicine').
    Also add the total sum of the spend by category wise. 
    """
    session = Session()
    try:
        query = session.query(ExpensiveTracker)

        # ✅ Filter by month (using cast for date type)
        if month:
            query = query.filter(cast(ExpensiveTracker.date, String).like(f"{month}%"))

        results = query.all()

        if not results:
            return {"status": "success", "message": "No records found"}

        data = []
        for item in results:
            record = {
                "date": item.date.strftime("%Y-%m-%d"),
                "description": item.description,
            }

            # ✅ If user wants a specific category, pick only that one
            if category in ["education", "travel", "food", "fruit", "medicine", "friends"]:
                record[category] = getattr(item, category)
            else:
                # otherwise, return all category columns
                record.update({
                    "education": item.education,
                    "travel": item.travel,
                    "food": item.food,
                    "fruit": item.fruit,
                    "medicine": item.medicine,
                    "friends": item.friends
                })
            data.append(record)

        return {"status": "success", "count": len(data), "data": data}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        session.close()

@mcp.tool(name="UpdatingItem", description="Update an existing expense record by ID.")
def UpdatingItem(
    id: int,
    date: str = None,
    education: int = None,
    travel: int = None,
    food: int = None,
    fruit: int = None,
    medicine: int = None,
    friends: int = None,
    description: str = None
):
    """
    Updates a record in the ExpensiveTracker table by ID or date.
    Only the fields provided will be updated.
    """
    session = Session()
    try:
        record = session.query(ExpensiveTracker).filter_by(id=id).first()
        if not record:
            return {"status": "error", "message": f"No record found with id={id}"}

        # ✅ Update only non-null fields
        if date: record.date = date
        if education is not None: record.education = education
        if travel is not None: record.travel = travel
        if food is not None: record.food = food
        if fruit is not None: record.fruit = fruit
        if medicine is not None: record.medicine = medicine
        if friends is not None: record.friends = friends
        if description: record.description = description

        record.created_at = datetime.now()  

        session.commit()
        return {"status": "success", "message": f"Record {id} updated successfully."}

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        session.close()

@mcp.tool(name="DeletingItem", description="Delete an expense record by ID.")
def DeletingItem(id: int):
    """
    Deletes a record from the ExpensiveTracker table by its ID or Date.
    """
    session = Session()
    try:
        record = session.query(ExpensiveTracker).filter_by(id=id).first()
        if not record:
            return {"status": "error", "message": f"No record found with id={id}"}

        session.delete(record)
        session.commit()

        return {"status": "success", "message": f"Record with id={id} deleted successfully."}

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        session.close()

if __name__ == "__main__":
    init_database()
    mcp.run(transport = "streamable-http", port = 8001)

# For Run
"""
uv run tools.py
uv run fastmcp dev tools.py
"""