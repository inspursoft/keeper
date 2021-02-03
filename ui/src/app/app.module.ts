import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';
import { ClarityModule } from '@clr/angular';
import { AppComponent } from './app.component';
import { JobComponent } from './job/job.component';
import { StageComponent } from './stage/stage.component';
import { AddNewComponent } from './add-new/add-new.component';
import { JobEditorComponent } from './job-editor/job-editor.component';
import { BoardComponentsLibraryModule } from 'board-components-library';
import { FormsModule } from '@angular/forms';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { HighlightComponent } from './shared/highlight/highlight.component';
import { AlertComponent } from './shared/alert/alert.component';
import { DialogComponent } from './shared/cs-dialog/cs-dialog.component';
import { GlobalAlertComponent } from './shared/cs-global-alert/cs-global-alert.component';
import { MessageService } from './shared/message.service';
import { StageEditorComponent } from './stage-editor/stage-editor.component';
import { ViewSelectorDirective } from './shared/class-base/view-selector.directive';
import { PreviewComponent } from './preview/preview.component';
import 'inspurprism';
import { AppService } from './app.service';
import { HttpClientModule } from '@angular/common/http';

@NgModule({
  declarations: [
    AppComponent,
    JobComponent,
    StageComponent,
    AddNewComponent,
    JobEditorComponent,
    HighlightComponent,
    AlertComponent,
    DialogComponent,
    GlobalAlertComponent,
    StageEditorComponent,
    ViewSelectorDirective,
    PreviewComponent
  ],
  imports: [
    BrowserModule,
    BrowserAnimationsModule,
    FormsModule,
    HttpClientModule,
    ClarityModule,
    BoardComponentsLibraryModule
  ],
  entryComponents: [
    JobComponent,
    StageComponent,
    AddNewComponent,
    JobEditorComponent,
    StageEditorComponent,
    AlertComponent,
    DialogComponent,
    PreviewComponent,
    GlobalAlertComponent,
  ],
  providers: [MessageService, AppService],
  bootstrap: [AppComponent]
})
export class AppModule {
}
