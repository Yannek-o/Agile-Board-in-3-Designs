from django.urls import path

from apps.backlog import views

app_name = "backlog"

ITEM = "items/<int:number>/"

urlpatterns = [
    path("", views.BacklogListView.as_view(), name="list"),
    path("plan/", views.BacklogPlanningView.as_view(), name="planning"),
    path("plan/move/", views.BacklogPlanMoveView.as_view(), name="plan_move"),
    path("new/", views.BacklogItemCreateView.as_view(), name="create"),
    path("epics/", views.EpicListView.as_view(), name="epics"),
    path("releases/", views.ReleaseListView.as_view(), name="releases"),
    path("filters/", views.SavedFilterCreateView.as_view(), name="save_filter"),
    path("bulk/", views.BulkEditView.as_view(), name="bulk"),
    path("export.csv", views.CsvExportView.as_view(), name="export_csv"),
    path("import/", views.CsvImportView.as_view(), name="import_csv"),
    path(
        "filters/<int:pk>/delete/",
        views.SavedFilterDeleteView.as_view(),
        name="delete_filter",
    ),
    path(
        "releases/<int:pk>/publish/",
        views.ReleasePublishView.as_view(),
        name="release_publish",
    ),
    path("reorder/", views.BacklogReorderView.as_view(), name="reorder"),
    path(ITEM, views.BacklogItemDetailView.as_view(), name="detail"),
    path(ITEM + "edit/", views.BacklogItemEditView.as_view(), name="edit"),
    path(ITEM + "inline/", views.ItemInlineUpdateView.as_view(), name="inline_update"),
    path(ITEM + "status/", views.ItemStatusView.as_view(), name="status"),
    path(ITEM + "archive/", views.ItemArchiveView.as_view(), name="archive"),
    path(
        ITEM + "restore/",
        views.ItemArchiveView.as_view(archive=False),
        name="restore",
    ),
    path(ITEM + "comments/", views.CommentCreateView.as_view(), name="comment"),
    path(ITEM + "links/", views.ItemLinkAddView.as_view(), name="link_add"),
    path(ITEM + "watch/", views.ItemWatchToggleView.as_view(), name="watch"),
    path(
        ITEM + "links/<int:pk>/delete/",
        views.ItemLinkDeleteView.as_view(),
        name="link_delete",
    ),
    path(ITEM + "web-links/", views.WebLinkAddView.as_view(), name="web_link_add"),
    path(ITEM + "work/", views.WorkLogCreateView.as_view(), name="log_work"),
    path(
        ITEM + "work/<int:pk>/delete/",
        views.WorkLogDeleteView.as_view(),
        name="delete_work_log",
    ),
    path(
        ITEM + "web-links/<int:pk>/delete/",
        views.WebLinkDeleteView.as_view(),
        name="web_link_delete",
    ),
    path(
        ITEM + "criteria/", views.CriterionAddView.as_view(), name="criterion_add"
    ),
    path(
        ITEM + "criteria/<int:pk>/toggle/",
        views.CriterionToggleView.as_view(),
        name="criterion_toggle",
    ),
    path(
        ITEM + "criteria/<int:pk>/delete/",
        views.CriterionDeleteView.as_view(),
        name="criterion_delete",
    ),
    path(
        ITEM + "attachments/",
        views.AttachmentUploadView.as_view(),
        name="attachment_upload",
    ),
    path(
        ITEM + "attachments/<int:pk>/",
        views.AttachmentDownloadView.as_view(),
        name="attachment_download",
    ),
]
