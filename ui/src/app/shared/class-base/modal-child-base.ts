import { OnDestroy, Output, ViewChild, ViewContainerRef } from '@angular/core';
import { Observable, Subject } from 'rxjs';
import { ComponentBase } from './component-base';
import { ViewSelectorDirective } from './view-selector.directive';

export class ModalChildBase extends ComponentBase implements OnDestroy {
  modalOpenedValue = false;
  @Output() closeNotification: Subject<any>;
  @ViewChild(ViewSelectorDirective) alertViewSelector;

  constructor() {
    super();
    this.closeNotification = new Subject<any>();
  }

  ngOnDestroy() {
    this.closeNotification.next();
    delete this.closeNotification;
  }

  set modalOpened(value: boolean) {
    this.modalOpenedValue = value;
    if (!value) {
      this.closeNotification.next();
    }
  }

  get modalOpened(): boolean {
    return this.modalOpenedValue;
  }

  openModal(): Observable<any> {
    this.modalOpened = true;
    return this.closeNotification.asObservable();
  }
}
