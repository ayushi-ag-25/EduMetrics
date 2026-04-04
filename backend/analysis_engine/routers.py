# ============================================================
#  analysis_engine/routers.py
#
#  Tells Django which database to use for which model.
#
#  Rule:
#    — Models from client_models.py  → 'client_db'   (read-only)
#    — Everything else               → 'default'      (analysis DB)
#
#  Add this to settings.py:
#      DATABASE_ROUTERS = ['analysis_engine.routers.EduMetricsRouter']
# ============================================================

CLIENT_MODELS = {
    'clientclass',
    'clientadvisor',
    'clientstudent',
    'clientsubject',
    'clientclasssubject',
    'clientsimstate',
    'clientattendance',
    'clientassignmentdefinition',
    'clientassignmentsubmission',
    'clientquizdefinition',
    'clientquizsubmission',
    'clientlibraryvisit',
    'clientbookborrow',
    'clientexamschedule',
    'clientexamresult',
}


class EduMetricsRouter:

    def db_for_read(self, model, **hints):
        if model._meta.model_name in CLIENT_MODELS:
            return 'client_db'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.model_name in CLIENT_MODELS:
            # Never write to the client DB — it's the college's data
            return None
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations within the same DB; block cross-DB relations
        db_set = {'client_db', 'default'}
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name in CLIENT_MODELS:
            return False   # never run migrations on client DB models
        return db == 'default'
