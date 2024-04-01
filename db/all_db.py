from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from db.db_connection import Base, engine

class UserInDB(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    role            = Column(String, nullable=False)
    username        = Column(String, unique=True, index=True)
    email           = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    phone           = Column(String, unique=True) 
    legal_address   = Column(String, nullable=True)
    user_city       = Column(String, nullable=True)
    user_department = Column(String, nullable=True)
    id_number       = Column(String, unique=True, index=True) #this will need a file
    tax_id          = Column(String, unique=True) #this will need a file
    score           = Column(String)  # Credit Score for Debtors, Money Laundry for Investors
    user_status     = Column(String)  #/ incomplete / complete / complete and verified    
    account_type    = Column(String)
    account_number  = Column(String)
    bank_name       = Column(String)
    agent           = Column(Boolean, default=False)   #THIS IS TRUE FOR INVESTMENT AGENTS ONLY
    added_by        = Column(Integer, ForeignKey("users.id"))
    
    

    owned_properties    = relationship("PropInDB", back_populates="owner")
    lent_mortgages      = relationship("MortgageInDB", foreign_keys="[MortgageInDB.lender_id]", back_populates="lender")
    borrowed_mortgages  = relationship("MortgageInDB", foreign_keys="[MortgageInDB.debtor_id]", back_populates="debtor")
    agent_mortgages     = relationship("MortgageInDB", foreign_keys="[MortgageInDB.agent_id]", back_populates="agent") # New line
    logs                = relationship("LogsInDb", back_populates="user")
    added_by_user       = relationship("UserInDB", foreign_keys=[added_by])
    
    affiliate_activities = relationship("AffiliateActivity", foreign_keys="[AffiliateActivity.affiliate_id]")
    referred_by_affiliate = relationship("AffiliateActivity", foreign_keys="[AffiliateActivity.referred_user_id]")

class AffiliatesInDb(Base):       # Not used
    __tablename__ = "affiliates"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    url         = Column(String, unique=True) 
    user_id     = Column(String, ForeignKey("users.id_number"))
    client_id   = Column(String, ForeignKey("users.id_number"))     

class RegsInDb(Base):
    __tablename__ = "registers"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    mortgage_id     = Column(Integer, ForeignKey("mortgages.id")) # Changed from MortgageInDB.id to mortgages.id
    lender_id       = Column(String, ForeignKey("users.id_number"))
    debtor_id       = Column(String, ForeignKey("users.id_number"))
    date            = Column(Date)
    paid            = Column(Integer) #NEW what user paid "debits" 
    concept         = Column(String)
    amount          = Column(Integer) #what system charges "credits"
    penalty         = Column(Integer)
    min_payment     = Column(Integer) # calculated by system
    limit_date      = Column(Date)
    to_main_balance = Column(Integer)         
    comprobante     = Column(String) #this will need a file
    payment_status  = Column(String, default='pending')  
    comment         = Column(String)    
    
    mortgage    = relationship("MortgageInDB", back_populates="registers")
    lender      = relationship("UserInDB", foreign_keys=[lender_id])
    debtor      = relationship("UserInDB", foreign_keys=[debtor_id])

class PropInDB(Base):
    __tablename__ = "properties" 
    id              = Column(Integer, primary_key=True, autoincrement=True)
    owner_id        = Column(String, ForeignKey("users.id_number"), nullable=False)
    matricula_id    = Column(String, unique=True) #this will need a pdf file
    address         = Column(String)
    neighbourhood   = Column(String)
    city            = Column(String)
    department      = Column(String)
    strate          = Column(Integer)
    area            = Column(Integer)
    type            = Column(String)
    tax_valuation   = Column(Integer) #this will need a file
    loan_solicited  = Column(Integer) 
    rate_proposed   = Column(Float)
    evaluation      = Column(String)
    study           = Column(String)    # NEW  "study" => "approved" 
    prop_status     = Column(String)    # available when study is approved or loaned ONLY
    comments        = Column(String)    # Loan tracking [received, analisis, concept, result, available]
    
    owner           = relationship("UserInDB", back_populates="owned_properties", foreign_keys=[owner_id])
    loan_progress   = relationship("LoanProgress", back_populates="property")


class MortgageInDB(Base): 
    __tablename__ = "mortgages"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    lender_id       = Column(String, ForeignKey("users.id_number"))
    debtor_id       = Column(String, ForeignKey("users.id_number"))
    agent_id        = Column(String, ForeignKey("users.id_number"), nullable=True) # Can be null, as there might be no agent
    matricula_id    = Column(String)
    start_date      = Column(Date)
    initial_balance = Column(Integer)
    interest_rate   = Column(Float)
    current_balance = Column(Integer)
    last_update     = Column(Date)
    monthly_payment = Column(Integer)
    mortgage_stage  = Column(String) #NEW [selected, notary, process, active]    
    mortgage_status = Column(String) # solicited => active, debt_pending, lawyer
    comments        = Column(String) # "Mortgage process submited by user='...' "] when selected status = in process

    lender      = relationship("UserInDB", foreign_keys=[lender_id], back_populates="lent_mortgages")
    debtor      = relationship("UserInDB", foreign_keys=[debtor_id], back_populates="borrowed_mortgages")
    agent       = relationship("UserInDB", foreign_keys=[agent_id], back_populates="agent_mortgages") 
    registers   = relationship("RegsInDb", back_populates="mortgage")

class LoanProgress(Base):
    __tablename__ = 'loan_progress'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    date        = Column(Date)
    property_id = Column(Integer, ForeignKey('properties.id'))  
    status      = Column(String) #["study", ...] ["process", ...]  
    user_id     = Column(String, ForeignKey('users.id_number')) 
    notes       = Column(String, nullable=True)
    updated_by  = Column(String, ForeignKey('users.id_number'))  

    property    = relationship("PropInDB", back_populates="loan_progress")
    user        = relationship("UserInDB", foreign_keys=[user_id])
    updater     = relationship("UserInDB", foreign_keys=[updated_by])
    
class AffiliateActivity(Base):
    __tablename__ = 'affiliate_activities'
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    affiliate_id        = Column(String, ForeignKey('users.id_number'))  # Link to UserInDB
    referred_user_id    = Column(String, ForeignKey('users.id_number'))  # Link to UserInDB
    activity_type       = Column(String)
    date                = Column(Date)
    details             = Column(String, nullable=True)
    status              = Column(String)

    affiliate       = relationship("UserInDB", foreign_keys=[affiliate_id])
    referred_user   = relationship("UserInDB", foreign_keys=[referred_user_id])


class PenaltyInDB(Base):
    __tablename__ = "penalty_interests"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    start_date      = Column(Date)
    end_date        = Column(Date)
    penalty_rate    = Column(Float)
    penalty_valid   = Column(Boolean)

class File(Base):
    __tablename__ = 'files'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    entity_type     = Column(String, nullable=False) 
    entity_id       = Column(Integer, nullable=False)    
    file_type       = Column(String, nullable=False)     
    file_location   = Column(String, nullable=False)

class LogsInDb(Base):
    __tablename__ = 'logs'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    action      = Column(String)
    timestamp   = Column(DateTime)
    message     = Column(String)
    user_id     = Column(String, ForeignKey("users.id_number"))

    user = relationship("UserInDB", back_populates="logs")
   

    
Base.metadata.create_all(bind=engine)
