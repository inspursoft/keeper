import { AfterViewInit, Component, OnDestroy, OnInit, ViewChild, ViewContainerRef } from '@angular/core';
import { Subject } from 'rxjs';
import { Job } from '../shared/shared.types';
import { ModalChildBase } from '../shared/class-base/modal-child-base';
import { MessageService } from '../shared/message.service';

@Component({
  selector: 'app-new-job',
  templateUrl: './job-editor.component.html',
  styleUrls: ['./job-editor.component.css']
})
export class JobEditorComponent extends ModalChildBase implements OnInit, AfterViewInit, OnDestroy {
  job: Job;
  editor: any;
  successNotification: Subject<Job>;
  @ViewChild('alertView', {read: ViewContainerRef}) alertView: ViewContainerRef;

  constructor(protected messageService: MessageService) {
    super();
    this.successNotification = new Subject();
  }

  ngOnInit() {

  }

  ngOnDestroy(): void {
    delete this.successNotification;
  }

  ngAfterViewInit(): void {
    const ace = Reflect.get(window, 'ace');
    const yamlScriptMode = ace.require('ace/mode/yaml').Mode;
    this.editor = ace.edit('compile-editor');
    ace.require('ace/ext/beautify');
    this.editor.setFontSize(16);
    this.editor.session.setMode(new yamlScriptMode());
    this.editor.setTheme('ace/theme/monokai');
    this.editor.setValue(this.job.code);
    ace.require('ace/ext/language_tools');
    this.editor.setOptions({
      enableBasicAutocompletion: true,
      enableSnippets: true,
      enableLiveAutocompletion: true
    });
  }

  cancel() {
    this.modalOpened = false;
  }

  save() {
    if (this.verifyInputExValid()) {
      const code = this.editor.getValue();
      if (!code || code === '') {
        this.messageService.showAlert('Job content can not empty', {
          view: this.alertView,
          alertType: 'warning'
        });
      } else {
        this.job.code = code;
        this.job.updateStage();
        this.successNotification.next(this.job);
        this.modalOpened = false;
      }
    }
  }

}
