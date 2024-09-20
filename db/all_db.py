from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Boolean, DateTime, BigInteger
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
    id_number       = Column(String, unique=True, index=True)
    tax_id          = Column(String, unique=True) 
    score           = Column(String) 
    civil_status    = Column(String) #for debtors alone
    user_status     = Column(String) #about info completion
    account_type    = Column(String) #bank savings...
    account_number  = Column(String)
    bank_name       = Column(String)
    agent           = Column(Boolean, default=False)
    added_by        = Column(Integer, ForeignKey("users.id"))

    owned_properties    = relationship("PropInDB", back_populates="owner")
    lent_mortgages      = relationship("MortgageInDB", foreign_keys="[MortgageInDB.lender_id]", back_populates="lender")
    borrowed_mortgages  = relationship("MortgageInDB", foreign_keys="[MortgageInDB.debtor_id]", back_populates="debtor")
    agent_mortgages     = relationship("MortgageInDB", foreign_keys="[MortgageInDB.agent_id]", back_populates="agent") # New line
    logs                = relationship("LogsInDb", back_populates="user")
    added_by_user       = relationship("UserInDB", foreign_keys=[added_by])
    
    affiliate_activities = relationship("AffiliateActivity", foreign_keys="[AffiliateActivity.affiliate_id]", back_populates="affiliate")
    referred_by_affiliate = relationship("AffiliateActivity", foreign_keys="[AffiliateActivity.referred_user_id]", back_populates="referred_user")

    
class RegsInDb(Base):
    __tablename__ = "registers"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    mortgage_id     = Column(Integer, ForeignKey("mortgages.id"))
    lender_id       = Column(String, ForeignKey("users.id_number"))
    debtor_id       = Column(String, ForeignKey("users.id_number"))
    date            = Column(Date)
    paid            = Column(BigInteger) #debits
    concept         = Column(String)
    amount          = Column(BigInteger)   #credits
    penalty         = Column(BigInteger)
    min_payment     = Column(BigInteger)
    limit_date      = Column(Date)
    to_main_balance = Column(BigInteger)         
    comprobante     = Column(String)
    payment_status  = Column(String)  
    comment         = Column(String)    
    payment_type    = Column(String)  #pse, transfer...
    
    mortgage    = relationship("MortgageInDB", back_populates="registers")
    lender      = relationship("UserInDB", foreign_keys=[lender_id])
    debtor      = relationship("UserInDB", foreign_keys=[debtor_id])

class PropInDB(Base):
    __tablename__ = "properties" 
    id              = Column(Integer, primary_key=True, autoincrement=True)
    owner_id        = Column(String, ForeignKey("users.id_number"), nullable=False)
    matricula_id    = Column(String, unique=True)
    address         = Column(String)
    neighbourhood   = Column(String)
    city            = Column(String)
    department      = Column(String)
    strate          = Column(Integer)
    area            = Column(Integer)
    type            = Column(String)
    tax_valuation   = Column(BigInteger)
    loan_solicited  = Column(BigInteger) 
    rate_proposed   = Column(Float)
    evaluation      = Column(String)
    study           = Column(String)
    prop_status     = Column(String)
    comments        = Column(String)
    observations    = Column(String) #new field
    youtube_link    = Column(String) #for videos of properties
    
    owner           = relationship("UserInDB", back_populates="owned_properties", foreign_keys=[owner_id])
    loan_progress   = relationship("LoanProgress", back_populates="property")

class MortgageInDB(Base): 
    __tablename__ = "mortgages"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    lender_id       = Column(String, ForeignKey("users.id_number"))
    debtor_id       = Column(String, ForeignKey("users.id_number"))
    agent_id        = Column(String, ForeignKey("users.id_number"), nullable=True)
    matricula_id    = Column(String)
    start_date      = Column(Date)
    initial_balance = Column(BigInteger)
    interest_rate   = Column(Float)
    current_balance = Column(BigInteger)
    last_update     = Column(Date)
    monthly_payment = Column(BigInteger)
    mortgage_stage  = Column(String)    
    mortgage_status = Column(String)
    comments        = Column(String)
    strategy        = Column(String)  #for lenders (acummulate, monthly payment, reinvest)

    lender      = relationship("UserInDB", foreign_keys=[lender_id], back_populates="lent_mortgages")
    debtor      = relationship("UserInDB", foreign_keys=[debtor_id], back_populates="borrowed_mortgages")
    agent       = relationship("UserInDB", foreign_keys=[agent_id], back_populates="agent_mortgages") 
    registers   = relationship("RegsInDb", back_populates="mortgage")

class LoanProgress(Base):
    __tablename__ = 'loan_progress'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    date        = Column(Date)
    property_id = Column(Integer, ForeignKey('properties.id'))  
    status      = Column(String)  
    user_id     = Column(String, ForeignKey('users.id_number')) 
    notes       = Column(String, nullable=True)
    updated_by  = Column(String, ForeignKey('users.id_number'))  

    property    = relationship("PropInDB", back_populates="loan_progress")
    user        = relationship("UserInDB", foreign_keys=[user_id])
    updater     = relationship("UserInDB", foreign_keys=[updated_by])
    
class AffiliateActivity(Base):    #not used
    __tablename__ = 'affiliate_activities'
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    affiliate_id        = Column(String, ForeignKey('users.id_number'))
    referred_user_id    = Column(String, ForeignKey('users.id_number'))
    activity_type       = Column(String)
    date                = Column(Date)
    details             = Column(String, nullable=True)
    status              = Column(String)

    affiliate = relationship("UserInDB", foreign_keys="[AffiliateActivity.affiliate_id]", back_populates="affiliate_activities")
    referred_user = relationship("UserInDB", foreign_keys="[AffiliateActivity.referred_user_id]", back_populates="referred_by_affiliate")
    
class PenaltyInDB(Base):
    __tablename__ = "penalty_interests"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    start_date      = Column(Date)
    end_date        = Column(Date)
    penalty_rate    = Column(Float)
    penalty_valid   = Column(Boolean)

class File(Base):    #to keep files
    __tablename__ = 'files'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    entity_type     = Column(String, nullable=False) 
    entity_id       = Column(Integer, nullable=False)    
    file_type       = Column(String, nullable=False)     
    file_location   = Column(String, nullable=False)

class LogsInDb(Base):  #to make popups with info
    __tablename__ = 'logs'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    action      = Column(String)
    timestamp   = Column(DateTime)
    message     = Column(String)
    user_id     = Column(String, ForeignKey("users.id_number"))

    user = relationship("UserInDB", back_populates="logs")
   
class NotificationsInDb(Base):    #To track enable and disable mail notifications
    __tablename__ = "notifications"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(String, ForeignKey("users.id_number"))
   #notification    = Column(String)    #class of notification OPTIONAL TO USE 
    activated       = Column(Boolean, default=False)  
    last_update     = Column(Date)  

class ComisionsInDb(Base):   #Set comisions, make a component to make the calculations BEFORE send it to backend
    __tablename__ = "comisions"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    concept         = Column(String)
    value           = Column(Float) #this is a percentage
    date            = Column(Date)
    rel_entity_type = Column(String)  #AGENT LOAN, AGENT INVESTOR, AFFILIATE MARKETER...
    
class AccountInDb(Base):  #INVESTORS ONLY, WHO DECIDE TO ACCUMULATE REVENUE
    __tablename__ = "accounts"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(String, ForeignKey("users.id_number"))
    total_balance   = Column(BigInteger)
    available       = Column(BigInteger)
    pending         = Column(BigInteger)
    #date           = Column(Date)
    #credits        = Column(BigInteger)
    #debits         = Column(BigInteger)
    #deductions     = Column(BigInteger)   #COSTS
    #taxes          = Column(BigInteger)   #RETENTIONS
    account_type    = Column(String)
    created_at      = Column(DateTime)
    
class LenderRegsInDb(Base):    
    __tablename__ = "lender_regs"
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    mortgage_id         = Column(Integer, ForeignKey("mortgages.id"))
    lender_id           = Column(String, ForeignKey("users.id_number"))
    previous_balance    = Column(BigInteger)
    new_balance         = Column(BigInteger)
    date                = Column(Date)
    amount              = Column(BigInteger)
    concept             = Column(String)
    comprobante         = Column(String)
    comment             = Column(String)
    
    
class AgentRegsInDb(Base):
    __tablename__ = "agent_regs"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    mortgage_id     = Column(Integer, ForeignKey("mortgages.id"))
    agent_id        = Column(String, ForeignKey("users.id_number"))
    previous_balance = Column(BigInteger)
    new_balance      = Column(BigInteger)
    date            = Column(Date)
    amount          = Column(BigInteger)  #DELETE
    #credits        = Column(BigInteger)
    #debits         = Column(BigInteger)
    #deductions     = Column(BigInteger)   #COSTS
    #taxes          = Column(BigInteger)   #RETENTIONS
    concept         = Column(String)
    comprobante     = Column(String)
    comment         = Column(String)
    
    
class MortgageRegsInDb(Base):
    __tablename__ = "mortgage_regs"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    mortgage_id     = Column(Integer, ForeignKey("mortgages.id"))
    lender_id       = Column(String, ForeignKey("users.id_number"))
    previous_balance = Column(BigInteger)
    new_balance      = Column(BigInteger)
    date            = Column(Date)
    amount          = Column(BigInteger)
    concept         = Column(String)
    comprobante     = Column(String)
    comment         = Column(String)
    
    
class LawyerRegsInDb(Base): #to track lawyers comissions
    __tablename__ = "lawyer_regs"
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    mortgage_id         = Column(Integer, ForeignKey("mortgages.id"))
    lawyer_id           = Column(String, ForeignKey("users.id_number"))
    previous_balance    = Column(BigInteger)
    new_balance         = Column(BigInteger)
    date                = Column(Date)
    amount              = Column(BigInteger)
    concept             = Column(String)
    comprobante         = Column(String)
    comment             = Column(String)
    

class CompanyRegsInDb(Base):   #to Track business incomes and expenses
    __tablename__ = "company_transactions"
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    company_id          = Column(String, ForeignKey("users.id_number"))
    type                = Column(String)  #credit, debit 
    prev_balance        = Column(BigInteger)
    date                = Column(Date)
    concept             = Column(String)     
    amount              = Column(BigInteger)
    new_balance         = Column(BigInteger)
    rel_entity_id       = Column(Integer)  
    rel_entity_type     = Column(String)  
    comprobante         = Column(String)  
    
Base.metadata.create_all(bind=engine)
